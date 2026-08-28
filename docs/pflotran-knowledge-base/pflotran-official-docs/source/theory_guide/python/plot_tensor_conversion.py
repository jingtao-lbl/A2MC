#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Oct 16 14:53:14 2020

@author: gehammo
"""

import matplotlib.pyplot as plt
import numpy as np

n = 1000
kx = 2e-12
ky = 1e-12

angle = np.arange(0,n+1)/float(n)*np.pi/2
x = np.cos(angle)
y = np.sin(angle)

k_linear = x[:]*kx + y[:]*ky
k_flow = np.power(x[:],2)*kx + np.power(y[:],2)*ky
k_potential = 1./(np.power(x[:],2)/kx+np.power(y[:],2)/ky)

f = plt.figure(figsize=(6,6))
ax = f.add_subplot(111)
plt.xlabel(r"$\theta$",fontsize=16)
plt.ylabel(r"$k$ $[m^2]$",fontsize=16,labelpad=10)

ax.plot(angle,k_linear,label='Linear')
ax.plot(angle,k_flow,label='Flow')
ax.plot(angle,k_potential,label='Potential')

unit = 0.125
x_tick = np.arange(0,0.5+unit,unit)
#x_label = [r"{\fontsize{15pt}{3em}\selectfont{}$0$}", r"$\frac{\pi}{8}$", r"$\frac{\pi}{4}$", r"$\frac{3\pi}{8}$", r"$\frac{\pi}{2}$"]
x_label = [r"$0$", r"$\frac{\pi}{8}$", r"$\frac{\pi}{4}$", r"$\frac{3\pi}{8}$", r"$\frac{\pi}{2}$"]
ax.set_xticks(x_tick*np.pi)
ax.set_xticklabels(x_label,fontsize=16)
ax.tick_params(axis='x',labelsize=16,pad=10)
ax.tick_params(axis='y',labelsize=16)


plt.legend(loc=1,fontsize=16)
plt.gca().get_legend().draw_frame(False)
plt.gca().get_legend().draw_frame(False)

f.subplots_adjust(hspace=0.2,wspace=0.2,
                  bottom=.14,top=.96,
                  left=.15,right=.96)

plt.show()
plt.savefig("tensor_to_scalar.png")
