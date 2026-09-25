"""GraphEmulator: values on the nodes of a declared, irregular network (gcn, gat; static or temporal).

THE property of a declared network: with L graph layers a node can be informed by nodes at most L
hops away and by nothing further. Asserted on the network directly, by perturbing one node's input,
for both layer types and for L = 1 and 2, with a negative control that a fully connected network
would break it. Accuracy is guarded too, and the temporal form is checked for causality.
"""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="GraphEmulator needs torch")

from models.surrogate._nn import per_case_channel_r2                   # noqa: E402
from models.surrogate.graphs import GraphEmulator, build_adjacency     # noqa: E402
from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec  # noqa: E402
from models.surrogate.tiers import load                                # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore:.*epoch budget", "ignore:.*unstamped provenance")

N_NODES = 8
CHAIN = [(i, i + 1) for i in range(N_NODES - 1)]
POS = np.linspace(0, 1, N_NODES, dtype="f4")[:, None]


def _spec():
    return SurrogateSpec(name="graph", use_mode="online_inference", tier="S2",
                         input_names=("a", "b"), input_lower=(0.0,) * 2, input_upper=(1.0,) * 2,
                         targets=(TargetSpec("h"),), provenance=Provenance(model="test"))


def _theta(n, seed):
    return np.random.default_rng(seed).uniform(0, 1, size=(n, 2))


def _static(X):
    return (X[:, [0]] * np.sin(np.pi * POS.T * (1 + X[:, [1]])))[:, None, :].astype("f4")


def _changed_nodes(net, node, n_in):
    # ON THE NET'S OWN DEVICE. `fit` moves the network to the GPU when there is one, so a probe
    # built on the CPU raises "Expected all tensors to be on the same device" rather than asserting
    # anything -- and this helper backs every reach test in this file, so on a GPU node the L-hop
    # property had no live assertion at all (found 2026-09-22; the sibling test_kgml_emulator.py
    # resolves the device the same way). An ERROR is not a pass, but it is not a check either.
    dev = next(net.parameters()).device
    x = torch.zeros(1, N_NODES, n_in, device=dev)
    y = x.clone()
    y[0, node] = 3.0
    with torch.no_grad():
        d = (net(y) - net(x)).abs().sum(-1)[0]
    return set(np.flatnonzero(d.cpu().numpy() > 1e-6).tolist())


@pytest.mark.parametrize("arch", ["gcn", "gat"])
def test_each_layer_type_LEARNS_a_static_network_field(arch):
    X, Xt = _theta(100, 0), _theta(30, 1)
    m = GraphEmulator(_spec(), N_NODES, edges=CHAIN, node_features=POS, arch=arch, width=32,
                      layers=2, epochs=250, patience=40).fit(X, node_values=_static(X))
    score = per_case_channel_r2(_static(Xt), m.predict_nodes(Xt), 0.9, ["h"])["h"]
    assert score["r2"] > 0.8, (arch, score)


@pytest.mark.parametrize("arch", ["gcn", "gat"])
@pytest.mark.parametrize("layers", [1, 2])
def test_a_node_is_informed_by_EXACTLY_the_nodes_within_L_hops(arch, layers):
    m = GraphEmulator(_spec(), N_NODES, edges=CHAIN, node_features=POS, arch=arch, width=16,
                      layers=layers, epochs=1, patience=5).fit(_theta(12, 0),
                                                              node_values=_static(_theta(12, 0)))
    net = m._net.eval()
    assert _changed_nodes(net, 0, net.inp.in_features) == set(range(layers + 1))


def test_a_FULLY_CONNECTED_network_WOULD_fail_that_test():
    """Negative control: the same one-layer network on a complete graph lets node 0 reach every node."""
    complete = [(i, j) for i in range(N_NODES) for j in range(i + 1, N_NODES)]
    m = GraphEmulator(_spec(), N_NODES, edges=complete, node_features=POS, arch="gcn", width=16,
                      layers=1, epochs=1, patience=5).fit(_theta(12, 0),
                                                         node_values=_static(_theta(12, 0)))
    net = m._net.eval()
    assert _changed_nodes(net, 0, net.inp.in_features) == set(range(N_NODES))


def _temporal(X, drv):
    D = len(drv)
    out = np.zeros((len(X), 1, D, N_NODES), "f4")
    for i, (a, b) in enumerate(X):
        h = np.zeros(N_NODES)
        for t in range(D):
            new = h.copy()
            new[0] += drv[t, 0] * (0.5 + a)
            new[1:] += (0.3 + 0.4 * b) * (h[:-1] - h[1:])
            h = 0.9 * new
            out[i, 0, t] = h
    return out


def test_the_TEMPORAL_form_learns_and_is_CAUSAL():
    drv = np.random.default_rng(0).random((16, 1)).astype("f4")
    X, Xt = _theta(80, 0), _theta(20, 1)
    m = GraphEmulator(_spec(), N_NODES, edges=CHAIN, node_features=POS, arch="gcn",
                      driver_names=["q"], width=24, layers=1, chunk_steps=5, epochs=60,
                      patience=20, batch_size=16).fit(X, node_values=_temporal(X, drv), drivers=drv)
    P = m.predict_nodes(Xt, drv)
    assert per_case_channel_r2(_temporal(Xt, drv), P, 0.9, ["h"])["h"]["r2"] > 0.8
    later = drv.copy()
    later[8:] = later[8:] * 4.0 + 1.0
    Q = m.predict_nodes(Xt[:3], later)
    assert np.array_equal(P[:3, :, :8], Q[:, :, :8]), "a step saw its own future"
    assert not np.allclose(P[:3, :, 8:], Q[:, :, 8:])


def test_it_round_trips_through_the_GENERIC_loader(tmp_path):
    drv = np.random.default_rng(0).random((10, 1)).astype("f4")
    X = _theta(12, 0)
    m = GraphEmulator(_spec(), N_NODES, adjacency=build_adjacency(N_NODES, edges=CHAIN) * 2.0,
                      node_features=POS, arch="gat", driver_names=["q"], width=16, layers=1,
                      epochs=2, patience=5).fit(X, node_values=_temporal(X, drv), drivers=drv)
    m.save(tmp_path / "art")
    back = load(tmp_path / "art", strict=False)
    assert isinstance(back, GraphEmulator) and back.temporal and back.arch == "gat"
    assert np.array_equal(m.predict_nodes(X[:3], drv), back.predict_nodes(X[:3], drv))


def test_refusals():
    with pytest.raises(ValueError, match="exactly one of"):
        GraphEmulator(_spec(), N_NODES)
    with pytest.raises(ValueError, match="outside"):
        GraphEmulator(_spec(), N_NODES, edges=[(0, N_NODES)])
    asym = np.zeros((N_NODES, N_NODES))
    asym[0, 1] = 1.0
    with pytest.raises(ValueError, match="symmetric"):
        GraphEmulator(_spec(), N_NODES, adjacency=asym)
    with pytest.raises(ValueError, match="no edges"):
        GraphEmulator(_spec(), N_NODES, adjacency=np.eye(N_NODES))
    with pytest.raises(ValueError, match="divisible by nhead"):
        GraphEmulator(_spec(), N_NODES, edges=CHAIN, arch="gat", width=30, nhead=4)
    static = GraphEmulator(_spec(), N_NODES, edges=CHAIN)
    X = _theta(6, 0)
    with pytest.raises(ValueError, match="declared static"):
        static.fit(X, node_values=_static(X), drivers=np.zeros((5, 1), "f4"))
    with pytest.raises(ValueError, match="node_values must be"):
        static.fit(X, node_values=_static(X)[:, :, :-1])
