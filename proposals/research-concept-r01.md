<!-- proposal-workspace:artifact:v1 -->
# Matemática de la propuesta CREDA

Este documento reúne únicamente la formulación matemática y las explicaciones presentadas en el artículo para **Conditional Rényi $\alpha$-Entropy Domain Adaptation (CREDA)**. La notación, las definiciones y las convenciones de las ecuaciones se conservan de acuerdo con el manuscrito.

## 1. Fundamentos de métodos de kernel

Los métodos de kernel permiten desarrollar algoritmos no lineales mediante el mapeo implícito de los datos desde su espacio original $\mathcal X$ hacia un espacio de características $\mathcal H$, de dimensión alta o incluso infinita, mediante una transformación no lineal

$$
\Phi:\mathcal X\rightarrow\mathcal H.
$$

El espacio $\mathcal H$ es un espacio de Hilbert con kernel reproductor (RKHS). La transformación $\Phi$ se elige de modo que los patrones complejos de los datos puedan resultar más simples, por ejemplo, linealmente separables en $\mathcal H$.

Como calcular explícitamente las coordenadas $\Phi(x)$ puede ser costoso o inviable, se define una función de kernel

$$
\kappa:\mathcal X\times\mathcal X\rightarrow\mathbb R
$$

que calcula el producto interno entre dos puntos en el espacio de características:

$$
\kappa(x_i,x_j)=\langle\Phi(x_i),\Phi(x_j)\rangle_{\mathcal H}.
\tag{1}
$$

De esta forma se trabaja directamente con el kernel, sin necesitar la forma explícita de $\Phi$ ni la estructura de $\mathcal H$. El kernel gaussiano empleado en el artículo es

$$
\kappa_\sigma(x_i,x_j)
=\exp\left(-\frac{\lVert x_i-x_j\rVert_2^2}{2\sigma^2}\right),
\qquad \sigma\in\mathbb R^+.
\tag{2}
$$

Este kernel corresponde a un espacio de características de dimensión infinita. Su tratabilidad matemática y su interpretación intuitiva como medida de similitud motivan su uso.

## 2. Estimación de la entropía de Rényi basada en kernels

Sea $X$ una variable aleatoria continua con función de densidad de probabilidad $f(x)$. La entropía de Rényi de orden $\alpha$ se define como

$$
H_\alpha(X)
=\frac{1}{1-\alpha}
\log\int_{\mathcal X}f(x)^\alpha\,dx,
\qquad \alpha>0,\quad \alpha\neq1.
\tag{3}
$$

En aplicaciones prácticas, especialmente para características profundas de alta dimensión, la densidad $f(x)$ es desconocida. Para evitar este problema se utiliza una ventana de Parzen, también conocida como estimación de densidad por kernels (KDE). Dado un conjunto de $N$ muestras $\{x_i\in X\}_{i=1}^N$, la densidad en un punto $x$ se estima mediante

$$
\hat f(x)=\frac{1}{N}\sum_{i=1}^N\kappa_\sigma(x,x_i).
\tag{4}
$$

El kernel gaussiano se selecciona por su simplicidad matemática y sus propiedades de suavizado.

### 2.1. Entropía cuadrática y potencial de información

Para $\alpha=2$, se obtiene el caso denominado entropía cuadrática de Rényi. El término

$$
\int f(x)^2\,dx
$$

se conoce como potencial de información (IP) y mide la información promedio contenida en la distribución. Al sustituir el estimador KDE en dicha integral se obtiene

$$
\begin{aligned}
\hat V_2(X)
&=\int\hat f(x)^2\,dx\\
&=\int
\left(\frac{1}{N}\sum_{i=1}^N\kappa_\sigma(x,x_i)\right)
\left(\frac{1}{N}\sum_{j=1}^N\kappa_\sigma(x,x_j)\right)dx\\
&=\frac{1}{N^2}\sum_{i=1}^N\sum_{j=1}^N
\int\kappa_\sigma(x,x_i)\kappa_\sigma(x,x_j)\,dx.
\end{aligned}
\tag{5}
$$

Para el kernel gaussiano, la integral anterior tiene una solución cerrada basada en la propiedad de convolución de las gaussianas:

$$
\int\kappa_\sigma(x,x_i)\kappa_\sigma(x,x_j)\,dx
=\kappa_{\sqrt{2}\sigma}(x_i,x_j).
\tag{6}
$$

Por tanto, el estimador del potencial de información se reduce a una expresión basada únicamente en las interacciones por pares entre las muestras:

$$
\hat V_2(X)
=\frac{1}{N^2}\sum_{i=1}^N\sum_{j=1}^N
\kappa_{\sqrt{2}\sigma}(x_i,x_j).
\tag{7}
$$

Sea $\mathbf K\in\mathbb R^{N\times N}$ la matriz de Gram con elementos

$$
K_{ij}=\kappa_{\sqrt{2}\sigma}(x_i,x_j).
$$

La suma de todos sus elementos es $\mathbf 1^\top\mathbf K\mathbf 1$, donde $\mathbf 1$ es un vector columna de unos. Así, el estimador matricial del potencial de información es

$$
\hat V_2(X)=\frac{1}{N^2}\mathbf 1^\top\mathbf K\mathbf 1.
\tag{8}
$$

### 2.2. Entropía de Rényi basada en matrices

La entropía de Rényi puede definirse directamente sobre el espectro de una matriz de Gram normalizada. Si

$$
\mathbf A=\frac{\mathbf K}{\operatorname{tr}(\mathbf K)},
$$

entonces

$$
H_\alpha(\mathbf A)
=\frac{1}{1-\alpha}\log\left(\operatorname{tr}(\mathbf A^\alpha)\right)
=\frac{1}{1-\alpha}\log\left(
\sum_i\breve\lambda_i(\mathbf A)^\alpha
\right),
\tag{9}
$$

donde $\breve\lambda_i(\mathbf A)$ son los valores propios de $\mathbf A$.

Para $\alpha=2$, el trabajo utiliza una forma computacionalmente estable basada en la norma de Frobenius:

$$
H_2(\mathbf A)=-\log\operatorname{tr}(\mathbf A^\top\mathbf A).
$$
con

$$
\operatorname{tr}(\mathbf A)=1,\qquad\lVert\mathbf A\rVert_F^2=\operatorname{tr}(\mathbf A^\top\mathbf A).
$$
El artículo destaca tres propiedades de esta formulación matricial:

- **No paramétrica:** no presupone una distribución para los datos y resulta apropiada para los espacios de características complejos y de alta dimensión aprendidos por redes neuronales.

- **Diferenciable:** la pérdida de entropía depende de los elementos de la matriz de Gram, que a su vez son funciones diferenciables de los vectores de características. Esto permite retropropagar gradientes a través de los cálculos del kernel y entrenar el modelo de extremo a extremo.

- **Robusta:** la entropía se calcula a partir de la estructura geométrica colectiva capturada por todas las interacciones por pares de la matriz de Gram. Por ello, los valores atípicos tienen un efecto limitado sobre la suma global de valores del kernel.

### 2.3. Entropía conjunta, información mutua y entropía condicional

El marco matricial se extiende a dos variables aleatorias $X$ y $Y$, representadas mediante pares de vectores de características

$$
\{\mathbf f_{X,i},\mathbf f_{Y,i}\}_{i=1}^N.
$$

Sean $\mathbf K_X,\mathbf K_Y\in\mathbb R^{N\times N}$ sus matrices de Gram. La matriz conjunta se define mediante el producto de Hadamard:

$$
\mathbf K_{XY}=\mathbf K_X\odot\mathbf K_Y,
\qquad
\breve{\mathbf K}_{X,Y}
=\frac{\mathbf K_{X,Y}}{\operatorname{tr}(\mathbf K_{X,Y})}.
$$

La matriz conjunta captura la similitud entre pares de muestras en el espacio conjunto de características.

La entropía conjunta es

$$
H_\alpha(\mathbf K_X,\mathbf K_Y)
=\frac{1}{1-\alpha}
\log\left(
\operatorname{tr}(\breve{\mathbf K}_{X,Y})^\alpha
\right).
\tag{10}
$$

La información mutua cuantifica la dependencia estadística entre ambas variables y se define como

$$
I_\alpha(\mathbf K_X;\mathbf K_Y)
=H_\alpha(\mathbf K_X)
+H_\alpha(\mathbf K_Y)
-H_\alpha(\mathbf K_X,\mathbf K_Y).
\tag{11}
$$

Cada término de entropía se calcula a partir de su matriz de Gram normalizada. Maximizar la información mutua es un objetivo habitual en aprendizaje de representaciones porque favorece que una representación retenga información sobre una variable relevante.

La entropía condicional mide la incertidumbre restante en $X$ cuando se conoce $Y$:

$$
H_\alpha(\mathbf K_X\mid\mathbf K_Y)
=H_\alpha(\mathbf K_X,\mathbf K_Y)
-H_\alpha(\mathbf K_Y).
\tag{12}
$$

Minimizar la entropía condicional equivale a hacer que $X$ sea más predecible a partir de $Y$.

## 3. Formulación de CREDA

CREDA está diseñado para entrenamiento de extremo a extremo en adaptación de dominio no supervisada. El marco utiliza un extractor profundo de características

$$
\mathcal F:\mathcal X\rightarrow\mathbb R^d
$$

que transforma una imagen de entrada

$$
\mathbf x\in\mathbb R^{\breve H\times\breve W\times\breve C},
\qquad
\mathcal X\subseteq\mathbb R^{p'},
\qquad
p'=\breve H\times\breve W\times\breve C,
$$

en un vector de características $\mathbf f\in\mathbb R^d$:

$$
\mathbf f=\mathcal F(\mathbf x)
=\left(
\breve f_L\circ\breve f_{L-1}\circ\cdots\circ\breve f_1
\right)(\mathbf x).
\tag{13}
$$

Aquí, $\breve f_l(\cdot)$ es la capa $l$-ésima del extractor, $l\in\{1,\ldots,L\}$, y $\circ$ es el operador de composición de funciones.

El clasificador

$$
\mathcal G:\mathbb R^d\rightarrow[0,1]^C
$$

predice el vector de probabilidades de clase $\mathbf g\in[0,1]^C$:

$$
\mathbf g=\mathcal G(\mathbf f)
=\left(
\breve g_{\breve L}\circ\breve g_{\breve L-1}
\circ\cdots\circ\breve g_1
\right)(\mathbf f),
\tag{14}
$$

donde $\breve g_{l'}(\cdot)$ representa una capa del clasificador, $l'\in\breve L$, y

$$
\sum_{c=1}^C g_c=1,
\qquad g_c\in\mathbf g.
$$

### 3.1. Dominios fuente y objetivo
#### Dominios fuente y objetivo, sujetos y bolsas de instancias

Cada sujeto es una bolsa, sus registros son instancias y su etiqueta es de nivel de sujeto.

Se dispone de un dominio fuente etiquetado

$$
\mathcal D_{\mathrm{bag}}^s=\{(B_i^s,y_i^s)\}_{i=1}^{N_s},\qquad B_i^s=\{x_{i,a}^s\}_{a=1}^{m_i^s}\in\mathsf B_{\mathrm{fin}}(\mathcal X),\qquad y_i^s\in\{0,1\}^C.
$$
con

$$
\sum_{c=1}^C y_{i,c}^s=1,\qquad i\in\{1,\ldots,N_s\}.
$$
$$
y_{i,c}^s\in\{0,1\},\qquad y_{i,c}^sy_{i,c'}^s=0\quad\text{para }c\ne c',\qquad c,c'\in\{1,\ldots,C\}.
$$
y de un dominio objetivo no etiquetado

$$
\mathcal D_{\mathrm{bag}}^t=\{B_j^t\}_{j=1}^{N_t},\qquad B_j^t=\{x_{j,b}^t\}_{b=1}^{m_j^t}\in\mathsf B_{\mathrm{fin}}(\mathcal X),\qquad m_j^t\in\mathbb N_{\geq1}.
$$
Para cada bolsa $B_i^r$, con $r\in\{s,t\}$, el codificador de registros es $\mathcal F:\mathcal X\to\mathbb R^d$ y la agregación por bolsa es

$$
\mathcal A:\bigsqcup_{m\geq1}(\mathbb R^d)^m\to\mathbb R^d,\qquad\mathbf z_i^r:=\frac{1}{m_i^r}\sum_{a=1}^{m_i^r}\mathcal F(x_{i,a}^r),\qquad r\in\{s,t\}.
\tag{14a}
$$

La unión disjunta admite cardinalidad finita positiva y la agregación es invariante a permutaciones. La predicción de bolsa es $\mathbf g_i^r:=\mathcal G(\mathbf z_i^r)\in\Delta_C$, donde $\Delta_C:=\{\mathbf v\in[0,1]^C:\sum_{c=1}^Cv_c=1\}$. Sea $\tau$ una regla fija de desempate; entonces $\tilde y_j^t:=\tau(\mathbf g_j^t)$, $S_c:=\{i:y_{i,c}^s=1\}$, $T_c:=\{j:\tilde y_j^t=c\}$, $n_c^s:=|S_c|$ y $n_c^t:=|T_c|$. Las etiquetas verdaderas se observan solo en $\mathcal D_{\mathrm{bag}}^s$.

Con $\zeta_\sigma\in\mathbb R$ y $0<\sigma_{\min}<\sigma_{\max}<\infty$, se aprende la escala positiva

$$
\sigma(\zeta_\sigma)=\sigma_{\min}+(\sigma_{\max}-\sigma_{\min})\operatorname{sigmoid}(\zeta_\sigma)\in(\sigma_{\min},\sigma_{\max}).
\tag{14b}
$$

La acotación excluye escalas nulas e infinitas, sin establecer identificabilidad.Para cada clase $c$, se calculan las matrices de kernel de fuente, objetivo y fuente–objetivo:

$$
\mathbf K_c^s\in\mathbb R^{n_c^s\times n_c^s},
\qquad
\mathbf K_c^t\in\mathbb R^{n_c^t\times n_c^t},
\qquad
\mathbf K_c^{st}\in\mathbb R^{n_c^t\times n_c^s}.
$$

Sus elementos se definen mediante

$$
\mathbf K_c^s\in\mathbb R^{n_c^s\times n_c^s},\qquad[\mathbf K_c^s]_{ii'}=\kappa_{\sigma(\zeta_\sigma)}(\mathbf z_i^s,\mathbf z_{i'}^s),\qquad i,i'\in S_c,\qquad y_{i,c}^s=1.
\tag{15}
$$
$$
\mathbf K_c^t\in\mathbb R^{n_c^t\times n_c^t},\qquad[\mathbf K_c^t]_{jj'}=\kappa_{\sigma(\zeta_\sigma)}(\mathbf z_j^t,\mathbf z_{j'}^t),\qquad j,j'\in T_c,\qquad\tilde y_j^t=c,\qquad\mathbf g_j^t=\mathcal G(\mathbf z_j^t).
\tag{16}
$$
y

$$
\mathbf K_c^{st}\in\mathbb R^{n_c^t\times n_c^s},\qquad[\mathbf K_c^{st}]_{ji}=\kappa_{\sigma(\zeta_\sigma)}(\mathbf z_j^t,\mathbf z_i^s),\qquad i\in S_c,\ j\in T_c,\qquad y_{i,c}^s=1,\quad\tilde y_j^t=c.
\tag{17}
$$
Además,

$$
g_{j,c}^t\in\mathbf g_j^t,\qquad\mathbf g_j^t=\mathcal G(\mathbf z_j^t).
$$
El valor $n_c^s$ es el número de muestras de $\mathcal D^s$ para las cuales $y_{i,c}^s=1$. De manera análoga, $n_c^t$ es el número de entradas objetivo que satisfacen $\arg\max_{c'}g_{j,c'}^t=c$.En esta construcción, las muestras y entradas contadas por $n_c^s$ y $n_c^t$ son bolsas; la asignación objetivo se determina mediante $\tilde y_j^t$.

### 3.2. Ponderación de pseudoetiquetas mediante entropía

Para mejorar la robustez frente a pseudoetiquetas ruidosas del conjunto objetivo, el artículo introduce un esquema de ponderación de confianza derivado de una medida de incertidumbre basada en entropía.

La incertidumbre del vector de probabilidades $\mathbf g_j^t\in[0,1]^C$ se cuantifica mediante su entropía cuadrática de Rényi:

$$
\hat H_2(\mathbf g_j^t)
=-\log\left(
\sum_{c=1}^C(g_{j,c}^t)^2
\right).
\tag{18}
$$

Para obtener una medida comparable, esta entropía se normaliza por su máximo teórico. Dicho máximo ocurre para una distribución uniforme:

$$
H_{2,\max}
=-\log\left(
\sum_{c=1}^C\left(\frac{1}{C}\right)^2
\right)
=\log(C).
$$

La incertidumbre normalizada es

$$
\hat U(\mathbf g_j^t)
=\frac{\hat H_2(\mathbf g_j^t)}{\log(C)},
\qquad
\hat U(\mathbf g_j^t)\in[0,1].
$$

A partir de ella se define el peso de confianza

$$
w_j^t=1-\hat U(\mathbf g_j^t),
\qquad
\mathbf w^t\in\mathbb R^{N_t}.
\tag{19}
$$

Este mecanismo reduce la ponderación de las predicciones ambiguas.

Para cada clase se construye la matriz de ponderación objetivo

$$
\tilde{\mathbf W}_c^t
=\tilde{\mathbf w}_c^t(\tilde{\mathbf w}_c^t)^\top,
\tag{20}
$$
La supervisión MIL usa solo la fuente:

$$
\mathcal L_{\mathrm{src}}=-\frac{1}{N_s}\sum_{i=1}^{N_s}\sum_{c=1}^Cy_{i,c}^s\log g_{i,c}^s.
\tag{20a}
$$

Con $\mathbf q_j^t:=\operatorname{sg}(\mathbf g_j^t)$, $\eta\in\mathbb R$, $0<\rho_{\min}<\rho_{\max}<1$ y $\mathbf u_C:=(1/C,\ldots,1/C)$,

$$
\rho(\eta)=\rho_{\min}+(\rho_{\max}-\rho_{\min})\operatorname{sigmoid}(\eta),\qquad\bar{\mathbf q}_j^t=(1-\rho(\eta))\mathbf q_j^t+\rho(\eta)\mathbf u_C.
\tag{20b}
$$

La mezcla preserva el orden, por lo que $\tilde y_j^t=\tau(\bar{\mathbf q}_j^t)$. Con $C\geq2$,

$$
\hat H_2(\bar{\mathbf q}_j^t)=-\log\sum_{c=1}^C(\bar q_{j,c}^t)^2,\qquad w_j^t:=1-\frac{\hat H_2(\bar{\mathbf q}_j^t)}{\log C},\qquad\tilde{\mathbf W}_c^t:=\tilde{\mathbf w}_c^t(\tilde{\mathbf w}_c^t)^\top,\quad\tilde{\mathbf w}_c^t:=(w_j^t)_{j\in T_c}.
\tag{20c}
$$
donde

$$
\tilde{\mathbf w}_c^t
=\left\{
w_j^t:\arg\max_{c'}g_{j,c'}^t=c
\right\}
\in\mathbb R^{n_c^t}.
$$

### 3.3. Regularización condicional por clase

El componente central de CREDA es un término de regularización que impone la alineación entre las distribuciones condicionales por clase de los dominios fuente y objetivo. Para ello se emplean el estimador de información mutua basado en entropía cuadrática de Rényi y el esquema de ponderación de confianza anterior:

$$
\tilde{\mathrm I}_2
(\mathbf K_c^s;\tilde{\mathbf K}_c^t)
=\frac{1}{2}\left(
H_2(\mathbf K_c^s)+H_2(\tilde{\mathbf K}_c^t)
\right)
-H_2(\mathbf K_c^{\mathrm{mix}}),
\tag{21}
$$
Siempre que las trazas sean positivas,

$$
\tilde{\mathbf K}_c^t:=\mathbf K_c^t\odot\tilde{\mathbf W}_c^t,\quad\mathbf A_c^s:=\frac{\mathbf K_c^s}{\operatorname{tr}(\mathbf K_c^s)},\quad\tilde{\mathbf A}_c^t:=\frac{\tilde{\mathbf K}_c^t}{\operatorname{tr}(\tilde{\mathbf K}_c^t)},\quad\tilde{\mathrm I}_2^{\mathrm{bag}}:=\frac12\left(H_2(\mathbf A_c^s)+H_2(\tilde{\mathbf A}_c^t)\right)-H_2\!\left(\frac{\mathbf K_c^{\mathrm{mix}}}{\operatorname{tr}(\mathbf K_c^{\mathrm{mix}})}\right).
\tag{21a}
$$

Esta puntuación se desea maximizar, sin afirmar no negatividad, cotas o comparabilidad entre cardinalidades.
donde

$$
\tilde{\mathbf K}_c^t
=\mathbf K_c^t\odot\tilde{\mathbf W}_c^t
$$

y

$$
\mathbf K_c^{\mathrm{mix}}
=
\begin{pmatrix}
\mathbf K_c^s & \mathbf K_c^{st}\\
(\mathbf K_c^{st})^\top & \tilde{\mathbf K}_c^t
\end{pmatrix}.
\tag{22}
$$

La matriz por bloques permite calcular el estimador de información mutua incluso cuando los tamaños de muestra de fuente y objetivo son diferentes, es decir, cuando

$$
n_c^t\neq n_c^s.
$$

### 3.4. Función de pérdida completa

La pérdida completa de CREDA integra la entropía cruzada supervisada sobre los datos fuente etiquetados con el regularizador de información mutua basado en la entropía cuadrática de Rényi:

$$
\mathcal L_{\mathrm{CREDA}}
=\sum_{i=1}^{N_s}\sum_{c=1}^C
y_{i,c}^s
\log\left(
\mathcal G(\mathcal F(\mathbf x_i^s))
\right)
-\lambda\sum_{c\in C}
\tilde{\mathrm I}_2
(\mathbf K_c^s;\tilde{\mathbf K}_c^t),
\tag{23}
$$
Sea $\mathcal C_{\mathrm{act}}$ el conjunto de clases con tamaños, pesos y normalizaciones positivos. Con $\pi_c\in[0,1]$, $\sum_{c=1}^C\pi_c=1$ y $\lambda\in[0,\infty)$,

$$
\mathcal L_{\mathrm{CREDA}}^{\mathrm{bag}}=\mathcal L_{\mathrm{src}}-\lambda\sum_{c\in\mathcal C_{\mathrm{act}}}\pi_c\tilde{\mathrm I}_2^{\mathrm{bag}}.
\tag{23a}
$$

No se presuponen no negatividad, convexidad, diferenciabilidad global, minimizadores ni convergencia.
donde $\lambda\in\mathbb R^+$ es un hiperparámetro que controla la intensidad de la alineación de dominios.

## Supuestos y obligaciones matemáticas pendientes

- Especificar regularidad para $\mathcal F$, $\mathcal A$ y $\mathcal G$.
- Probar invariancia a permutaciones y semidefinición positiva del kernel de bolsas.
- Establecer buena definición, rango y propiedades de $\tilde{\mathrm I}_2^{\mathrm{bag}}$.
- Analizar trazas positivas, clases vacías, pesos nulos y estabilidad por minibatches.
- Caracterizar no suavidades de pseudoetiquetas, empates, $\sigma(\zeta_\sigma)$ y $\rho(\eta)$.
- Dar cotas, minimizadores y contraejemplos para $\mathcal L_{\mathrm{CREDA}}^{\mathrm{bag}}$.