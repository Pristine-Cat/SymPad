# SymPad

SymPad is a simple symbolic calculator using SymPy for the math and MathJax for the display in a web browser. It runs as a private http server on your machine and executes the system default browser pointing to itself on startup.
User input is intended to be quick, easy and intuitive and is displayed in symbolic form as it is being entered.
Sympad will accept LaTeX math formatting as well as Python expressions (or a mix) and evaluate the result symbolically or numerically. The following are all valid inputs:
```
sin (3\pi / 2)
cos**-1 x
\log_2{8}
\lim_{x \to \infty} 1/x
Limit (1/x, x, 0, dir='-')
\sum_{n=0}^oo x^n / n!
\sum_{n=1}**10 Sum (\sum_{l=1}^m l, (m, 1, n))
Derivative (\int dx, x)
d**6 / dxdy**2dz**3 x^3 y^3 z^3
Integral (e^{-x^2}, (x, 0, \infty))
\int_0^1 \int_0^x \int_0^y 1 dz dy dx
\int_0^\infty e^{-st} dt
{{1,2},{3,4}}**-1
det({{sin x, -cos x},{cos x, sin x}})
\begin{matrix} A & B \\ C & D \end{matrix} * {x, y}
expand {x+1}**2
factor (x^3 + 3x^2 + 3x + 1)
series (e^x, x, 1, 9)
```

## Installation

SymPad has one dependancy which must be installed on your system in order to run which is the SymPy Python package: [https://sympy.org/](https://sympy.org/).
Apart from that, if you just want to use the program you will only need the file **sympad.py**. This is an autogenerated Python script which contains all the modules (apart from SymPy) and web resources in one handy file.

Otherwise if you want to play with the code then download everything and run the program using **server.py**.

If you want to regenerate the parser tables you will need the PLY Python package: [https://www.dabeaz.com/ply/](https://www.dabeaz.com/ply/).

## Open-Source License

SymPad is made available under the BSD license, you may use it as you wish, as long as you copy the BSD statement if you redistribute it (see the LICENSE file for details).
