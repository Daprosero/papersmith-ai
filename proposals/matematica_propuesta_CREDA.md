# Matemática de la propuesta CREDA

Este documento reúne únicamente la formulación matemática y las explicaciones presentadas en el artículo para **Conditional Rényi \(\alpha\)-Entropy Domain Adaptation (CREDA)**. La notación, las definiciones y las convenciones de las ecuaciones se conservan de acuerdo con el manuscrito.

## 1. Fundamentos de métodos de kernel

Los métodos de kernel permiten desarrollar algoritmos no lineales mediante el mapeo implícito de los datos desde su espacio original \(\mathcal X\) hacia un espacio de características \(\mathcal H\), de dimensión alta o incluso infinita, mediante una transformación no lineal

$$
\Phi:\mathcal X\rightarrow\mathcal H.
$$

El espacio \(\mathcal H\) es un espacio de Hilbert con kernel reproductor (RKHS). La transformación \(\Phi\) se elige de modo que los patrones complejos de los datos puedan resultar más simples, por ejemplo, linealmente separables en \(\mathcal H\).

Como calcular explícitamente las coordenadas \(\Phi(x)\) puede ser costoso o inviable, se define una función de kernel

$$
\kappa:\mathcal X\times\mathcal X\rightarrow\mathbb R
$$

que calcula el producto interno entre dos puntos en el espacio de características:

$$
\kappa(x_i,x_j)=\langle\Phi(x_i),\Phi(x_j)\rangle_{\mathcal H}.
\tag{1}
$$

De esta forma se trabaja directamente con el kernel, sin necesitar la forma explícita de \(\Phi\) ni la estructura de \(\mathcal H\). El kernel gaussiano empleado en el artículo es

$$
\kappa_\sigma(x_i,x_j)
=\exp\left(-\frac{\lVert x_i-x_j\rVert_2^2}{2\sigma^2}\right),
\qquad \sigma\in\mathbb R^+.
\tag{2}
$$

Este kernel corresponde a un espacio de características de dimensión infinita. Su tratabilidad matemática y su interpretación intuitiva como medida de similitud motivan su uso.

## 2. Estimación de la entropía de Rényi basada en kernels

Sea \(X\) una variable aleatoria continua con función de densidad de probabilidad \(f(x)\). La entropía de Rényi de orden \(\alpha\) se define como

$$
H_\alpha(X)
=\frac{1}{1-\alpha}
\log\int_{\mathcal X}f(x)^\alpha\,dx,
\qquad \alpha>0,\quad \alpha\neq1.
\tag{3}
$$

En aplicaciones prácticas, especialmente para características profundas de alta dimensión, la densidad \(f(x)\) es desconocida. Para evitar este problema se utiliza una ventana de Parzen, también conocida como estimación de densidad por kernels (KDE). Dado un conjunto de \(N\) muestras \(\{x_i\in X\}_{i=1}^N\), la densidad en un punto \(x\) se estima mediante

$$
\hat f(x)=\frac{1}{N}\sum_{i=1}^N\kappa_\sigma(x,x_i).
\tag{4}
$$

El kernel gaussiano se selecciona por su simplicidad matemática y sus propiedades de suavizado.

### 2.1. Entropía cuadrática y potencial de información

Para \(\alpha=2\), se obtiene el caso denominado entropía cuadrática de Rényi. El término

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

Sea \(\mathbf K\in\mathbb R^{N\times N}\) la matriz de Gram con elementos

$$
K_{ij}=\kappa_{\sqrt{2}\sigma}(x_i,x_j).
$$

La suma de todos sus elementos es \(\mathbf 1^\top\mathbf K\mathbf 1\), donde \(\mathbf 1\) es un vector columna de unos. Así, el estimador matricial del potencial de información es

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

donde \(\breve\lambda_i(\mathbf A)\) son los valores propios de \(\mathbf A\).

Para \(\alpha=2\), el trabajo utiliza una forma computacionalmente estable basada en la norma de Frobenius:

$$
H_2(\mathbf A)
=-\log\left(
\operatorname{tr}(\breve{\mathbf A}^{\top}\breve{\mathbf A})
\right),
$$

con

$$
\breve{\mathbf A}=\frac{\mathbf A}{\operatorname{tr}(\mathbf A)},
\qquad
\operatorname{tr}(\breve{\mathbf A})=1,
\qquad
\lVert\mathbf A\rVert_F^2
=\operatorname{tr}(\mathbf A^\top\mathbf A).
$$

El artículo destaca tres propiedades de esta formulación matricial:

- **No paramétrica:** no presupone una distribución para los datos y resulta apropiada para los espacios de características complejos y de alta dimensión aprendidos por redes neuronales.

- **Diferenciable:** la pérdida de entropía depende de los elementos de la matriz de Gram, que a su vez son funciones diferenciables de los vectores de características. Esto permite retropropagar gradientes a través de los cálculos del kernel y entrenar el modelo de extremo a extremo.

- **Robusta:** la entropía se calcula a partir de la estructura geométrica colectiva capturada por todas las interacciones por pares de la matriz de Gram. Por ello, los valores atípicos tienen un efecto limitado sobre la suma global de valores del kernel.

### 2.3. Entropía conjunta, información mutua y entropía condicional

El marco matricial se extiende a dos variables aleatorias \(X\) y \(Y\), representadas mediante pares de vectores de características

$$
\{\mathbf f_{X,i},\mathbf f_{Y,i}\}_{i=1}^N.
$$

Sean \(\mathbf K_X,\mathbf K_Y\in\mathbb R^{N\times N}\) sus matrices de Gram. La matriz conjunta se define mediante el producto de Hadamard:

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

La entropía condicional mide la incertidumbre restante en \(X\) cuando se conoce \(Y\):

$$
H_\alpha(\mathbf K_X\mid\mathbf K_Y)
=H_\alpha(\mathbf K_X,\mathbf K_Y)
-H_\alpha(\mathbf K_Y).
\tag{12}
$$

Minimizar la entropía condicional equivale a hacer que \(X\) sea más predecible a partir de \(Y\).

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

en un vector de características \(\mathbf f\in\mathbb R^d\):

$$
\mathbf f=\mathcal F(\mathbf x)
=\left(
\breve f_L\circ\breve f_{L-1}\circ\cdots\circ\breve f_1
\right)(\mathbf x).
\tag{13}
$$

Aquí, \(\breve f_l(\cdot)\) es la capa \(l\)-ésima del extractor, \(l\in\{1,\ldots,L\}\), y \(\circ\) es el operador de composición de funciones.

El clasificador

$$
\mathcal G:\mathbb R^d\rightarrow[0,1]^C
$$

predice el vector de probabilidades de clase \(\mathbf g\in[0,1]^C\):

$$
\mathbf g=\mathcal G(\mathbf f)
=\left(
\breve g_{\breve L}\circ\breve g_{\breve L-1}
\circ\cdots\circ\breve g_1
\right)(\mathbf f),
\tag{14}
$$

donde \(\breve g_{l'}(\cdot)\) representa una capa del clasificador, \(l'\in\breve L\), y

$$
\sum_{c=1}^C g_c=1,
\qquad g_c\in\mathbf g.
$$

### 3.1. Dominios fuente y objetivo

Se dispone de un dominio fuente etiquetado

$$
\mathcal D^s
=\left\{
\mathbf x_i^s\in\mathbb R^{p'},
\mathbf y_i^s\in\{0,1\}^C
\right\}_{i=1}^{N_s},
$$

con

$$
\sum_{c=1}^C y_{i,c}^s=1,
$$

$$
y_{i,c}^s\neq y_{i,c'}^s,
\qquad
c,c'\in C,
\qquad
y_{i,c}^s,y_{i,c'}^s\in\mathbf y_i^s,
$$

y de un dominio objetivo no etiquetado

$$
\mathcal D^t
=\left\{
\mathbf x_j^t\in\mathbb R^{p'}
\right\}_{j=1}^{N_t}.
$$

Para cada clase \(c\), se calculan las matrices de kernel de fuente, objetivo y fuente–objetivo:

$$
\mathbf K_c^s\in\mathbb R^{n_c^s\times n_c^s},
\qquad
\mathbf K_c^t\in\mathbb R^{n_c^t\times n_c^t},
\qquad
\mathbf K_c^{st}\in\mathbb R^{n_c^t\times n_c^s}.
$$

Sus elementos se definen mediante

$$
\mathbf K_c^s
=\left[
\kappa_{\sigma_s}(\mathbf f_i^s,\mathbf f_{i'}^s)
\right],
\quad
\forall i,i'\in n_c^s:
\quad
\mathbf f_i^s=\mathcal F(\mathbf x_i^s),
\quad
y_{i,c}^s=1,
\tag{15}
$$

$$
\mathbf K_c^t
=\left[
\kappa_{\sigma_t}(\mathbf f_j^t,\mathbf f_{j'}^t)
\right],
\quad
\forall j,j'\in n_c^t:
\quad
\mathbf f_j^t=\mathcal F(\mathbf x_j^t),
\quad
\arg\max_{c'}g_{j,c'}^t=c,
\tag{16}
$$

y

$$
\mathbf K_c^{st}
=\left[
\kappa_{\sigma_{st}}(\mathbf f_i^s,\mathbf f_j^t)
\right],
\quad
\forall i\in n_c^s,\ j\in n_c^t:
\quad
y_{i,c}^s=1,
\quad
\arg\max_{c'}g_{j,c'}^t=c.
\tag{17}
$$

Además,

$$
g_{j,c}^t\in\mathbf g_j^t,
\qquad
\mathbf g_j^t=\mathcal G(\mathbf f_j^t).
$$

El valor \(n_c^s\) es el número de muestras de \(\mathcal D^s\) para las cuales \(y_{i,c}^s=1\). De manera análoga, \(n_c^t\) es el número de entradas objetivo que satisfacen \(\arg\max_{c'}g_{j,c'}^t=c\).

### 3.2. Ponderación de pseudoetiquetas mediante entropía

Para mejorar la robustez frente a pseudoetiquetas ruidosas del conjunto objetivo, el artículo introduce un esquema de ponderación de confianza derivado de una medida de incertidumbre basada en entropía.

La incertidumbre del vector de probabilidades \(\mathbf g_j^t\in[0,1]^C\) se cuantifica mediante su entropía cuadrática de Rényi:

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

donde \(\lambda\in\mathbb R^+\) es un hiperparámetro que controla la intensidad de la alineación de dominios.

## 4. Cálculo por minibatches

Las matrices de kernel de CREDA se calculan dentro de cada minibatch de entrenamiento. Para un minibatch de muestras fuente y objetivo:

1. Se extraen las características y se generan las pseudoetiquetas de las muestras objetivo.

2. Para cada clase \(c\), se filtran los vectores de características de la fuente cuya etiqueta real es \(c\) y los vectores del objetivo cuya pseudoetiqueta es \(c\).

3. La matriz de kernel entre dominios \(\mathbf K_c^{st}\) se calcula evaluando el kernel gaussiano entre cada característica fuente filtrada y cada característica objetivo filtrada.

4. Las matrices dentro de cada dominio, \(\mathbf K_c^s\) y \(\mathbf K_c^t\), se calculan de forma análoga entre las características filtradas de sus dominios respectivos.

5. Si una clase no aparece en un minibatch, su contribución a la pérdida de regularización en ese paso de entrenamiento es cero.

Este procedimiento por minibatches y condicionado por clase permite una implementación eficiente y escalable del objetivo de alineación.

## 5. Justificación de \(\alpha=2\)

La selección de la entropía cuadrática de Rényi, \(\alpha=2\), se motiva por su conexión directa con el potencial de información. Bajo un kernel gaussiano, esta conexión convierte el objetivo de alineación en una meta geométricamente intuitiva.

El estimador basado en muestras de la Ecuación (7) es una suma de similitudes por pares. Por ello, minimizar la pérdida condicional por clase de CREDA equivale a favorecer que los vectores de características de una misma clase formen agrupaciones compactas y puras en el espacio de características, promoviendo directamente la separabilidad de las clases.

La pérdida CREDA también es sensible a estadísticas de orden superior y captura la estructura global de las distribuciones, incluida su dispersión y modalidad. Esto es relevante para alinear clases complejas y multimodales.

Finalmente, la formulación del estimador como un promedio de todas las interacciones por pares proporciona una estimación robusta de la similitud entre distribuciones por clase. Este promedio estabiliza las estimaciones del gradiente al reducir la influencia de valores atípicos individuales o pseudoetiquetas ruidosas.

## 6. Consistencia estadística y convergencia empírica

El artículo distingue entre la consistencia estadística del estimador y la convergencia empírica del modelo profundo durante el entrenamiento.

El estimador de información mutua de la Ecuación (21) hereda propiedades teóricas de la estimación por ventanas de Parzen. KDE es un estimador consistente: la densidad estimada converge a la densidad verdadera cuando el número de muestras tiende a infinito. En consecuencia, el potencial de información y el estimador completo de información mutua son también estimadores estadísticamente consistentes de la información mutua cuadrática de Rényi verdadera entre las distribuciones condicionales por clase.

Desde la perspectiva de optimización, la pérdida completa de CREDA no es convexa debido a la naturaleza altamente no lineal de los modelos profundos. Por tanto, no son posibles garantías formales de convergencia hacia un mínimo global, como ocurre habitualmente en sistemas de aprendizaje profundo.

No obstante, el método está diseñado para facilitar una convergencia empírica estable. El uso de un kernel gaussiano infinitamente diferenciable hace que el término de regularización sea suave y contribuye a un paisaje de pérdida adecuado para la optimización basada en gradientes.