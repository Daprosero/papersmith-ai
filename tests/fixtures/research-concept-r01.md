<!-- proposal-workspace:artifact:v1 -->
# Representative managed proposal

Neutral fixture used only to drive the paper-proposal engine tests. It carries no research content; every symbol and equation is illustrative.

## 1. Preliminaries

Let $\mathcal X$ be an input space mapped to a feature space $\mathcal H$ by $\Phi:\mathcal X\rightarrow\mathcal H$, with inner product

$$
\kappa(x_i,x_j)=\langle\Phi(x_i),\Phi(x_j)\rangle_{\mathcal H}.
\tag{1}
$$

## 2. Label constraints

Each source item $i$ carries a one-hot label over $C$ classes.

$$
\sum_{c=1}^C y_{i,c}^s=1,\qquad i\in\{1,\ldots,N_s\}.
$$
$$
y_{i,c}^s\in\{0,1\},\qquad y_{i,c}^sy_{i,c'}^s=0\quad\text{para }c\ne c',\qquad c,c'\in\{1,\ldots,C\}.
$$

The two constraints above define a valid one-hot encoding.

## 3. Objective

A generic empirical objective closes the fixture.

$$
\mathcal L=\frac{1}{N}\sum_{i=1}^{N}\ell\!\left(f(x_i),y_i\right).
\tag{2}
$$

Stable trailing paragraph.
