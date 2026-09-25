"""Emulators for values on an IRREGULAR NETWORK of nodes: monitoring wells, stream reaches, mesh cells.

    static    theta (N, P) [+ node features]                 ->  node values (N, C, n_nodes)
    temporal  theta (N, P) [+ node features] + drivers (D, F) ->  node values (N, C, D, n_nodes)

The network is DECLARED: undirected `edges` between node indices, or a symmetric non-negative
`adjacency` whose entries weight each connection (a conductance, an inverse distance). Node features
are properties of the nodes themselves (coordinates, porosity, elevation) and are part of the
model's world, so they are fixed at construction and saved with the artifact.

Two message-passing layers, one class:

  gcn   graph convolution (Kipf & Welling, 2017): each node mixes its neighbours through the
        symmetrically normalised adjacency with self-loops, D^-1/2 (A + I) D^-1/2. Honours edge
        WEIGHTS.
  gat   masked multi-head attention over nodes (Velickovic et al., 2018): each node attends to its
        declared neighbours and itself, and the weights are learned per pair. Uses the adjacency
        as a MASK only, so edge weights beyond "connected or not" are ignored.

THE PROPERTY BOTH MUST HOLD. With L graph layers, a node can be informed by nodes at most L hops
away, and by nothing further. That is what a declared network means, and the tests assert it on the
layers directly.

TEMPORAL MODE is a graph-temporal network: at each step the graph layers mix [inputs, previous
state] over the network, then a GRU cell shared by every node updates that node's state. Because the
state itself is passed along edges, a disturbance at one node travels one hop per graph layer per
step. The state is carried across training windows and through the whole record at prediction, as
in `spatiotemporal.py`, so the model is causal in time and its memory is not reset at chunk edges.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .base import BatchPrediction, HullGate, SurrogateModel
from .fields import _check_structured_spec
from .spec import SurrogateSpec
from ._nn import (REDUCTIONS, blocks, channel_stats, column_stats, fit_torch, minibatches,
                  reduce_channels, refuse_nonfinite, reload_device, resolve_device, validation_split)

VALID_GRAPH_ARCHS = ("gcn", "gat")


def build_adjacency(n_nodes: int, edges: Optional[Sequence[Tuple[int, int]]] = None,
                    adjacency: Optional[np.ndarray] = None) -> np.ndarray:
    """A dense, symmetric, non-negative (n, n) adjacency with a zero diagonal. Self-loops are added
    by the layers, so a declared self-edge is not needed and not kept."""
    if (edges is None) == (adjacency is None):
        raise ValueError("declare the network with exactly one of `edges` or `adjacency`")
    if edges is not None:
        A = np.zeros((n_nodes, n_nodes), dtype="f4")
        for e in edges:
            i, j = int(e[0]), int(e[1])
            if not (0 <= i < n_nodes and 0 <= j < n_nodes):
                raise ValueError(f"edge {tuple(e)} names a node outside 0..{n_nodes - 1}")
            A[i, j] = A[j, i] = 1.0
    else:
        A = np.asarray(adjacency, dtype="f4")
        if A.shape != (n_nodes, n_nodes):
            raise ValueError(f"adjacency must be ({n_nodes}, {n_nodes}), got {A.shape}")
        if not np.isfinite(A).all() or (A < 0).any():
            raise ValueError("adjacency must be finite and non-negative")
        if not np.allclose(A, A.T, atol=1e-6):
            raise ValueError("adjacency must be symmetric: this emulator's network is undirected")
        A = A.copy()
    np.fill_diagonal(A, 0.0)
    if not A.any():
        raise ValueError("the declared network has no edges; a graph emulator without edges is an "
                         "independent model per node")
    return A


class GraphEmulator(SurrogateModel):
    """theta [+ node features] [+ drivers(t)] -> values on declared nodes. See the module docstring."""

    def __init__(self, spec: SurrogateSpec, n_nodes: int,
                 edges: Optional[Sequence[Tuple[int, int]]] = None,
                 adjacency: Optional[np.ndarray] = None,
                 node_features: Optional[np.ndarray] = None,
                 node_feature_names: Sequence[str] = (), arch: str = "gcn",
                 driver_names: Optional[Sequence[str]] = None, width: int = 64, layers: int = 2,
                 nhead: int = 4, chunk_steps: Optional[int] = None,
                 nonneg: Optional[Sequence[str]] = None, reduce: str = "mean", epochs: int = 300,
                 batch_size: int = 32, lr: float = 1e-3, weight_decay: float = 1e-5,
                 val_fraction: float = 0.15, patience: int = 40, random_state: int = 0,
                 device: Optional[str] = None) -> None:
        self.nonneg = list(nonneg or [])
        self._names = _check_structured_spec(spec, self.nonneg, "GraphEmulator")
        super().__init__(spec)
        self.n_nodes = int(n_nodes)
        if self.n_nodes < 2:
            raise ValueError(f"a network needs at least 2 nodes, got {n_nodes}")
        self._adj = build_adjacency(self.n_nodes, edges, adjacency)
        arch = str(arch).lower()
        if arch not in VALID_GRAPH_ARCHS:
            raise ValueError(f"arch must be one of {VALID_GRAPH_ARCHS}, got {arch!r}")
        if arch == "gat" and int(width) % int(nhead):
            raise ValueError(f"gat needs width divisible by nhead; got width={width}, nhead={nhead}")
        self.node_feature_names = list(node_feature_names)
        if node_features is None:
            if self.node_feature_names:
                raise ValueError("node_feature_names given without node_features")
            self._nodef = np.zeros((self.n_nodes, 0), dtype="f4")
        else:
            nf = np.asarray(node_features, dtype="f4")
            if nf.ndim != 2 or nf.shape[0] != self.n_nodes:
                raise ValueError(f"node_features must be ({self.n_nodes}, F), got {nf.shape}")
            if not np.isfinite(nf).all():
                raise ValueError("node_features contain NaN or inf")
            if self.node_feature_names and len(self.node_feature_names) != nf.shape[1]:
                raise ValueError(f"{len(self.node_feature_names)} node_feature_names for "
                                 f"{nf.shape[1]} feature columns")
            self._nodef = nf
        self.driver_names = None if driver_names is None else list(driver_names)
        if self.driver_names is not None and not self.driver_names:
            raise ValueError("driver_names is empty; pass None for a static network emulator")
        if min(int(width), int(layers)) < 1:
            raise ValueError("width and layers must be at least 1")
        if chunk_steps is not None and int(chunk_steps) < 1:
            raise ValueError(f"chunk_steps must be at least 1, got {chunk_steps}")
        if reduce not in REDUCTIONS:
            raise ValueError(f"reduce must be one of {REDUCTIONS}, got {reduce!r}")
        self.arch = arch
        self.width, self.layers, self.nhead = int(width), int(layers), int(nhead)
        self.chunk_steps = None if chunk_steps is None else int(chunk_steps)
        self.reduce = reduce
        self.epochs, self.batch_size, self.lr = int(epochs), int(batch_size), float(lr)
        self.weight_decay, self.val_fraction = float(weight_decay), float(val_fraction)
        self.patience, self.random_state, self.device = int(patience), int(random_state), device
        self._net: Any = None
        self._gate = HullGate()
        self.history: List[Dict[str, float]] = []
        self.info: Dict[str, Any] = {}
        self.n_viable_train = 0

    @property
    def temporal(self) -> bool:
        return self.driver_names is not None

    # ---- network ----

    def _build(self, n_theta: int):
        B = blocks()
        torch, nn, F = B.torch, B.nn, B.F
        n, C, width, nhead = self.n_nodes, len(self._names), self.width, self.nhead
        A_hat = torch.as_tensor(self._adj) + torch.eye(n)
        dinv = A_hat.sum(1).rsqrt()
        norm = dinv[:, None] * A_hat * dinv[None, :]
        forbid = ~(A_hat > 0)
        temporal = self.temporal
        n_in = n_theta + self._nodef.shape[1] + (len(self.driver_names) if temporal else 0)

        class GCN(nn.Module):
            def __init__(self):
                super().__init__()
                self.lin = nn.Linear(width, width)
                self.norm_ = nn.LayerNorm(width)
                self.register_buffer("A", norm)

            def forward(self, h):                              # (B, n, w)
                return self.norm_(h + F.gelu(self.lin(torch.einsum("ij,bjw->biw", self.A, h))))

        class GAT(nn.Module):
            def __init__(self):
                super().__init__()
                self.attn = nn.MultiheadAttention(width, nhead, batch_first=True)
                self.norm_ = nn.LayerNorm(width)
                self.register_buffer("block", forbid)          # True where attention is FORBIDDEN

            def forward(self, h):
                m, _ = self.attn(h, h, h, attn_mask=self.block, need_weights=False)
                return self.norm_(h + m)

        Layer = GCN if self.arch == "gcn" else GAT
        layers = self.layers

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.inp = nn.Linear(n_in + (width if temporal else 0), width)
                self.graph = nn.ModuleList([Layer() for _ in range(layers)])
                self.cell = nn.GRUCell(width, width) if temporal else None
                self.head = nn.Linear(width, C)

            def encode(self, x):                               # (B, n, d) -> (B, n, w)
                h = F.gelu(self.inp(x))
                for g in self.graph:
                    h = g(h)
                return h

            def forward(self, x):                              # static: (B, n, n_in) -> (B, n, C)
                return self.head(self.encode(x))

            def step(self, x, state):                          # temporal: state (B, n, w)
                z = self.encode(torch.cat([x, state], -1))
                b, nn_, w = z.shape
                s = self.cell(z.reshape(b * nn_, w), state.reshape(b * nn_, w)).reshape(b, nn_, w)
                return self.head(s), s

        return Net()

    # ---- inputs ----

    def _node_inputs(self, torch, Xn_b, dev):
        """(B, n, P + F_node): theta repeated on every node, beside that node's own features."""
        b = Xn_b.shape[0]
        theta = Xn_b[:, None, :].expand(b, self.n_nodes, Xn_b.shape[1])
        nf = torch.as_tensor((self._nodef - self._nmu) / self._nsd, device=dev)
        return torch.cat([theta, nf[None].expand(b, *nf.shape)], -1)

    def _roll(self, torch, Xn_b, Mn_t, s, e, state, dev):
        static = self._node_inputs(torch, Xn_b, dev)
        outs = []
        for t in range(s, e):
            drv = Mn_t[t][None, None, :].expand(static.shape[0], self.n_nodes, Mn_t.shape[1])
            y, state = self._net.step(torch.cat([static, drv], -1), state)
            outs.append(y)
        return torch.stack(outs, 1), state                   # (B, T, n, C)

    def _drivers(self, drivers) -> np.ndarray:
        M = np.asarray(drivers, dtype="f4")
        if M.ndim != 2 or M.shape[1] != len(self.driver_names):
            raise ValueError(f"drivers must be (D, {len(self.driver_names)}), got {M.shape}")
        if not np.isfinite(M).all():
            raise ValueError("drivers contain NaN or inf")
        return M

    # ---- fit ----

    def fit(self, X: np.ndarray, Y: Optional[np.ndarray] = None,
            viable: Optional[np.ndarray] = None, node_values: Optional[np.ndarray] = None,
            drivers: Optional[np.ndarray] = None, verbose: bool = False) -> "GraphEmulator":
        import torch
        import torch.nn.functional as F

        if node_values is None:
            raise ValueError("GraphEmulator.fit needs `node_values`; Y is unused")
        if self.temporal and drivers is None:
            raise ValueError("this emulator was declared with driver_names; pass `drivers` (D, F)")
        if not self.temporal and drivers is not None:
            raise ValueError("drivers given, but this emulator was declared static (driver_names=None)")
        X = self._check_X(X)
        V = np.asarray(node_values, dtype="f4")
        M = self._drivers(drivers) if self.temporal else None
        want = ((len(X), len(self._names)) + ((M.shape[0],) if self.temporal else ())
                + (self.n_nodes,))
        if V.shape != want:
            raise ValueError(f"node_values must be {want}, got {V.shape}")
        if viable is None:
            viable = np.isfinite(V.reshape(len(V), -1)).all(axis=1)
        viable = np.asarray(viable, dtype=bool)
        refuse_nonfinite("GraphEmulator node_values", V[viable], rows=np.flatnonzero(viable))
        Xv, Vv = X[viable], V[viable]
        self.n_viable_train = len(Xv)
        if self.n_viable_train < 4:
            raise ValueError(f"only {self.n_viable_train} viable cases; need >= 4")
        self._gate.fit(Xv)

        self._xmu, self._xsd = column_stats(Xv)
        if self._nodef.shape[1]:
            self._nmu, self._nsd = column_stats(self._nodef)
        else:
            self._nmu = self._nsd = np.zeros((1, 0), dtype="f4")
        self._vmu, self._vsd = channel_stats(Vv)
        if self.temporal:
            self._mmu, self._msd = column_stats(M)
        dev = resolve_device(self.device)
        torch.manual_seed(self.random_state)
        self._net = self._build(Xv.shape[1]).to(dev)
        net = self._net
        Xt = torch.as_tensor(((Xv - self._xmu) / self._xsd).astype("f4"), device=dev)
        # channel axis last, to match the network's (B, [T,] n, C) output
        Vt = torch.as_tensor((Vv - self._vmu) / self._vsd, device=dev).movedim(1, -1)
        tr, va = validation_split(len(Xv), self.val_fraction, self.random_state)
        rng = np.random.default_rng(self.random_state)

        if not self.temporal:
            def static_loss(ii):
                it = torch.as_tensor(ii, device=dev)
                return F.mse_loss(net(self._node_inputs(torch, Xt[it], dev)), Vt[it])
            self.history, self.info = fit_torch(
                net, train_batches=lambda ep: minibatches(tr, self.batch_size, rng),
                val_batches=lambda: minibatches(va, self.batch_size), batch_loss=static_loss,
                epochs=self.epochs, lr=self.lr, weight_decay=self.weight_decay,
                patience=self.patience, verbose=verbose, label=f"GraphEmulator[{self.arch}]")
        else:
            Mt = torch.as_tensor((M - self._mmu) / self._msd, device=dev)
            D = M.shape[0]
            c = self.chunk_steps or D
            windows = [(s, min(s + c, D)) for s in range(0, D, c)]

            def zero(b):
                return torch.zeros(b, self.n_nodes, self.width, device=dev)

            def windows_loss(ii):
                it = torch.as_tensor(ii, device=dev)
                state = zero(len(it))
                for (s, e) in windows:
                    pred, state = self._roll(torch, Xt[it], Mt, s, e, state, dev)
                    yield F.mse_loss(pred, Vt[it][:, s:e])
                    state = state.detach()

            def full_loss(ii):
                it = torch.as_tensor(ii, device=dev)
                pred, _ = self._roll(torch, Xt[it], Mt, 0, D, zero(len(it)), dev)
                return F.mse_loss(pred, Vt[it])

            self.history, self.info = fit_torch(
                net, train_batches=lambda ep: minibatches(tr, self.batch_size, rng),
                val_batches=lambda: minibatches(va, self.batch_size), batch_loss=full_loss,
                step_hook=windows_loss, epochs=self.epochs, lr=self.lr,
                weight_decay=self.weight_decay, patience=self.patience, verbose=verbose,
                label=f"GraphEmulator[{self.arch}, temporal]")
        self._fit_device = dev
        net.eval()
        self.fitted = True
        return self

    # ---- predict ----

    def predict_nodes(self, X: np.ndarray, drivers: Optional[np.ndarray] = None) -> np.ndarray:
        """(N, C, n_nodes) static, or (N, C, D, n_nodes) temporal with the state carried throughout."""
        import torch
        self._check_fitted()
        X = self._check_X(X)
        dev = next(self._net.parameters()).device
        Xn = torch.as_tensor(((X - self._xmu) / self._xsd).astype("f4"), device=dev)
        chunks = []
        with torch.no_grad():
            if not self.temporal:
                if drivers is not None:
                    raise ValueError("this emulator is static; drivers are not an input")
                for a in range(0, len(X), 256):
                    chunks.append(self._net(self._node_inputs(torch, Xn[a:a + 256], dev)).cpu().numpy())
                out = np.concatenate(chunks).transpose(0, 2, 1)               # (N, C, n)
            else:
                if drivers is None:
                    raise ValueError("this emulator is driven by drivers(t); pass `drivers`")
                M = self._drivers(drivers)
                Mn = torch.as_tensor((M - self._mmu) / self._msd, device=dev)
                for a in range(0, len(X), 64):
                    xb = Xn[a:a + 64]
                    pred, _ = self._roll(torch, xb, Mn, 0, M.shape[0],
                                         torch.zeros(len(xb), self.n_nodes, self.width, device=dev), dev)
                    chunks.append(pred.cpu().numpy())
                out = np.concatenate(chunks).transpose(0, 3, 1, 2)            # (N, C, D, n)
        out = out * self._vsd + self._vmu
        for n in self.nonneg:
            j = self._names.index(n)
            np.clip(out[:, j], 0.0, None, out=out[:, j])
        return out

    def predict_batch(self, X: np.ndarray, drivers: Optional[np.ndarray] = None) -> BatchPrediction:
        X = self._check_X(X)
        vals = reduce_channels(self.predict_nodes(X, drivers), self.reduce)
        dist = self._gate.distance(X)
        return BatchPrediction(spec=self.spec, values=vals, in_hull=dist <= self._gate.threshold,
                               hull_distance=dist)

    # ---- persistence ----

    def _cfg(self) -> Dict[str, Any]:
        return {"n_nodes": self.n_nodes, "adjacency": self._adj.tolist(),
                "node_features": self._nodef.tolist() if self._nodef.shape[1] else None,
                "node_feature_names": self.node_feature_names, "arch": self.arch,
                "driver_names": self.driver_names, "width": self.width, "layers": self.layers,
                "nhead": self.nhead, "chunk_steps": self.chunk_steps, "nonneg": self.nonneg,
                "reduce": self.reduce, "epochs": self.epochs, "batch_size": self.batch_size,
                "lr": self.lr, "weight_decay": self.weight_decay,
                "val_fraction": self.val_fraction, "patience": self.patience,
                "random_state": self.random_state}

    def _save_artifacts(self, directory: Path) -> None:
        import torch
        sc = {"xmu": self._xmu, "xsd": self._xsd, "nmu": self._nmu, "nsd": self._nsd,
              "vmu": self._vmu, "vsd": self._vsd}
        if self.temporal:
            sc.update(mmu=self._mmu, msd=self._msd)
        torch.save({"state_dict": self._net.state_dict(), "cfg": self._cfg(),
                    "fit_device": getattr(self, "_fit_device", "cpu"), "scalers": sc,
                    "gate": self._gate, "history": self.history, "info": self.info,
                    "n_viable_train": self.n_viable_train}, Path(directory) / "graph.pt")
        (Path(directory) / "history.json").write_text(json.dumps(
            {"history": self.history, "info": self.info}, indent=2, default=float))


def load_graph(directory: Path, spec: SurrogateSpec, device: Optional[str] = None,
               strict: bool = True, check_env: bool = True) -> GraphEmulator:
    import torch
    from .environment import enforce_environment
    if check_env:
        enforce_environment(directory, strict=strict)
    blob = torch.load(Path(directory) / "graph.pt", weights_only=False, map_location="cpu")
    cfg = dict(blob["cfg"])
    adj = np.asarray(cfg.pop("adjacency"), dtype="f4")
    nf = cfg.pop("node_features")
    m = GraphEmulator(spec, adjacency=adj, node_features=None if nf is None else np.asarray(nf, "f4"),
                      **cfg)
    s = blob["scalers"]
    m._xmu, m._xsd, m._nmu, m._nsd = s["xmu"], s["xsd"], s["nmu"], s["nsd"]
    m._vmu, m._vsd = s["vmu"], s["vsd"]
    if m.temporal:
        m._mmu, m._msd = s["mmu"], s["msd"]
    m._gate, m.history, m.info = blob["gate"], blob["history"], blob["info"]
    m.n_viable_train = blob["n_viable_train"]
    dev = reload_device(device, blob.get("fit_device"))
    m._fit_device = blob.get("fit_device", "cpu")
    m._net = m._build(m._xmu.shape[1]).to(dev)
    m._net.load_state_dict({k: v.to(dev) for k, v in blob["state_dict"].items()})
    m._net.eval()
    m.fitted = True
    return m
