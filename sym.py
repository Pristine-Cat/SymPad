# Convert between internal AST and sympy expressions and write out LaTeX, simple and python code

# TODO: 'str'**x, 'str'!
# TODO: MatrixSymbol ('A', 2, 2)**n
# TODO: Multiple arguments in
# TODO: ImageSet(Lambda(n, 2 n pi + pi/2), Integers)
# TODO: PurePoly(lambda**4 - 11*lambda**3 + 29*lambda**2 + 35*lambda - 150, lambda, domain='ZZ')
# TODO: sequence(factorial(k), (k,1,oo))

import re
import sympy as sp

sp.numbers   = sp.numbers # medication for pylint
sp.boolalg   = sp.boolalg
sp.fancysets = sp.fancysets

from sast import AST # AUTO_REMOVE_IN_SINGLE_SCRIPT

_SYMPY_FLOAT_PRECISION = None
_USER_FUNCS            = set () # set or dict of user function names

_OPS                   = AST.OPS | {'Text'}
_NOPS                  = lambda ops: _OPS - ops

class AST_Text (AST): # for displaying elements we do not know how to handle, only returned from SymPy processing, not passed in
	op = 'text'

	def _init (self, tex, nat = None, py = None):
		self.tex, self.nat, self.py = tex, (tex if nat is None else nat), (tex if py is None else py)

class ExprDontDoIt (sp.Expr): # prevent doit() evaluation of expression a single time
	def doit (self, *args, **kwargs):
		return self.args [0]

def _tuple2ast_func_args (args):
	return args [0] if len (args) == 1 else AST (',', args)

def _ast_is_neg (ast):
	return ast.is_minus or ast.is_neg_num or (ast.is_mul and _ast_is_neg (ast.muls [0]))

def _ast_func_call (func, args):
	kw     = {}
	pyargs = []

	for arg in args:
		if arg.is_ass and arg.lhs.is_var:
			name = arg.lhs.as_identifier ()

			if name is not None:
				kw [name] = ast2spt (arg.rhs)
				continue

		pyargs.append (ast2spt (arg))

	return func (*pyargs, **kw)

def _trail_comma (obj):
	return ',' if len (obj) == 1 else ''

#...............................................................................................
def ast2tex (ast): # abstract syntax tree -> LaTeX text
	return _ast2tex_funcs [ast.op] (ast)

def _ast2tex_wrap (obj, curly = None, paren = None):
	s = ast2tex (obj) if isinstance (obj, AST) else str (obj)

	if (obj.op in paren) if isinstance (paren, set) else paren:
		return f'\\left({s} \\right)'

	if (obj.op in curly) if isinstance (curly, set) else curly:
		return f'{{{s}}}'

	return s

def _ast2tex_curly (ast):
	# return _ast2tex_wrap (ast, not ast.is_single_unit)
	return \
			f'{ast2tex (ast)}'                    if ast.is_single_unit else \
			f'{{{ast2tex (ast)}}}'                if not ast.is_comma else \
			f'{{\\left({ast2tex (ast)}\\right)}}'

def _ast2tex_paren (ast, ops = {}):
	return _ast2tex_wrap (ast, 0, not (ast.is_paren or (ops and ast.op not in ops)))
	# return ast2tex (ast) if ast.is_paren or (ops and ast.op not in ops) else f'\\left({ast2tex (ast)} \\right)'

def _ast2tex_paren_mul_exp (ast, ret_has = False, also = {'=', '+', 'lamb'}):
	if ast.is_mul:
		s, has = _ast2tex_mul (ast, True)
	else:
		s, has = ast2tex (ast), ast.op in also

	s = _ast2tex_wrap (s, 0, has) # f'\\left({s} \\right)' if has else s

	return (s, has) if ret_has else s

def _ast2tex_eq_hs (ast, hs, lhs = True):
	return _ast2tex_wrap (hs, 0, (hs.is_lamb or hs.is_ass or (lhs and hs.is_piece)) if ast.is_ass else {'=', 'piece', 'lamb'})

def _ast2tex_num (ast):
	m, e = ast.mant_and_exp

	return m if e is None else f'{m} \\cdot 10^{_ast2tex_curly (AST ("#", e))}'

_ast2tex_var_xlat = {'Naturals', 'Naturals0', 'Integers', 'Reals', 'Complexes'}

def _ast2tex_var (ast):
	if not ast.var:
		return '{}' # Null var

	if ast.var in _ast2tex_var_xlat:
		return sp.latex (getattr (sp, ast.var))

	v = ast.as_var.var
	p = ''

	while v [-6:] == '_prime':
		v, p = v [:-6], p + "'"

	n = v.replace ('_', '\\_')
	t = AST.Var.PY2TEX.get (n)

	return ( \
			t or n            if not ast.diff_or_part_type else
			f'd{t or n}'			if ast.is_diff_any else
			'\\partial'       if ast.is_part_solo else
			f'\\partial{t}'   if t else
			f'\\partial {n}'
	) + p

def _ast2tex_attr (ast):
	a = ast.attr.replace ('_', '\\_')
	a = a if ast.args is None else f'\\operatorname{{{a}}}{_ast2tex_paren (_tuple2ast_func_args (ast.args))}'

	return f'{_ast2tex_paren (ast.obj, {"=", "#", ",", "-", "+", "*", "/", "lim", "sum", "intg", "piece"})}.{a}'

def _ast2tex_mul (ast, ret_has = False):
	t   = []
	p   = None
	has = False

	for n in ast.muls:
		# s = _ast2tex_paren (n) if n.is_add or (n.is_piece and n is not ast.muls [-1]) or (p and _ast_is_neg (n)) else ast2tex (n)
		s = _ast2tex_wrap (n, \
				_ast_is_neg (n) or (n.is_intg and n is not ast.muls [-1]) or (n.strip_lim_sum ().is_intg and n is not ast.muls [-1]), \
				n.op in {'=', '+', "lamb"} or (n.is_piece and n is not ast.muls [-1]))

		if p and (n.op in {'!', '#', 'mat'} or n.is_null_var or p.op in {'lim', 'sum', 'diff', 'intg', 'mat'} or \
				(n.is_pow and n.base.is_pos_num) or (n.op in {'/', 'diff'} and p.op in {'#', '/'}) or _ast_is_neg (n) or \
				(p.is_div and (p.numer.is_diff_or_part_solo or (p.numer.is_pow and p.numer.base.is_diff_or_part_solo)))):
			t.append (f' \\cdot {s}')
			has = True

		elif p and (p.op in {'sqrt'} or \
				p.is_diff_or_part_solo or n.is_diff_or_part_solo or p.is_diff_or_part or n.is_diff_or_part or \
				(p.is_long_var and n.op not in {'(', '['}) or (n.is_long_var and p.op not in {'(', '['})):
			t.append (f'\\ {s}')
		else:
			t.append (f'{"" if not p else " "}{s}')

		p = n

	return (''.join (t), has) if ret_has else ''.join (t)

def _ast2tex_pow (ast, trighpow = True):
	# b = _ast2tex_curly (ast.base) if ast.base.is_mat else ast2tex (ast.base) # TODO: REMOVE
	b = _ast2tex_wrap (ast.base, {'mat'}, not (ast.base.op in {'@', '"', '(', '|', 'func', 'mat'} or ast.base.is_pos_num))
	p = _ast2tex_curly (ast.exp)

	if ast.base.is_trigh_func_noninv and ast.exp.is_single_unit and trighpow:
		i = len (ast.base.func) + (15 if ast.base.func in {'sech', 'csch'} else 1)

		return f'{b [:i]}^{p}{b [i:]}'

	return f'{b}^{p}'

	# if ast.base.op in {'@', '(', '|', 'mat'} or ast.base.is_pos_num: # TODO: REMOVE
	# 	return f'{b}^{p}'

	# return f'\\left({b} \\right)^{p}'

def _ast2tex_log (ast):
	return \
			f'\\ln{_ast2tex_paren (ast.log)}' \
			if ast.base is None else \
			f'\\log_{_ast2tex_curly (ast.base)}{_ast2tex_paren (ast.log)}'

_ast2tex_func_xlat = {
	'diag': True,
	'eye': True,
	'gamma': '\\Gamma',
	'ones': True,
	'zeros': True,
	'zeta': '\\zeta',
}

def _ast2tex_func (ast):
	act = _ast2tex_func_xlat.get (ast.func)

	if act is not None:
		try:
			if act is True:
				return ast2tex (spt2ast (_ast_func_call (getattr (sp, ast.func), ast.args)))

			return f'{act}{_ast2tex_paren (_tuple2ast_func_args (ast.args))}'

		except:
			pass

	if ast.is_trigh_func:
		n = (f'\\operatorname{{{ast.func [1:]}}}^{{-1}}' \
				if ast.func in {'asech', 'acsch'} else \
				f'\\{ast.func [1:]}^{{-1}}') \
				if ast.func [0] == 'a' else \
				(f'\\operatorname{{{ast.func}}}' if ast.func in {'sech', 'csch'} else f'\\{ast.func}')

		return f'{n}{_ast2tex_paren (_tuple2ast_func_args (ast.args))}'

	return \
			f'\\{ast.func}{_ast2tex_paren (_tuple2ast_func_args (ast.args))}' \
			if ast.func in AST.Func.TEX else \
			'\\operatorname{' + ast.func.replace ('_', '\\_') + f'}}{_ast2tex_paren (_tuple2ast_func_args (ast.args))}'

def _ast2tex_lim (ast):
	s = ast2tex (ast.to) if ast.dir is None else (_ast2tex_pow (AST ('^', ast.to, AST.Zero), trighpow = False) [:-1] + ast.dir)

	return f'\\lim_{{{ast2tex (ast.lvar)} \\to {s}}} {_ast2tex_paren_mul_exp (ast.lim)}'

def _ast2tex_sum (ast):
	return f'\\sum_{{{ast2tex (ast.svar)} = {ast2tex (ast.from_)}}}^{_ast2tex_curly (ast.to)} {_ast2tex_paren_mul_exp (ast.sum)}' \

_rec_diff_var_single_start = re.compile (r'^d(?=[^_])')

def _ast2tex_diff (ast):
	ds = set ()
	p  = 0

	for n in ast.dvs:
		if n.is_var:
			p += 1

			if n.var:
				ds.add (n)

		else: # n = ('^', ('@', 'diff or part'), ('#', 'int'))
			p += int (n.exp.num)
			ds.add (n.base)

	if not ds:
		return f'\\frac{{d}}{{}}{_ast2tex_paren (ast.diff)}'

	dv = next (iter (ds))

	if len (ds) == 1 and not dv.is_partial:
		return f'\\frac{{d{"" if p == 1 else f"^{p}"}}}{{{" ".join (ast2tex (n) for n in ast.dvs)}}}{_ast2tex_paren (ast.diff)}'

	else:
		s = ''.join (_rec_diff_var_single_start.sub (r'\\partial ', ast2tex (n)) for n in ast.dvs)

		return f'\\frac{{\\partial{"" if p == 1 else f"^{p}"}}}{{{s}}}{_ast2tex_paren (ast.diff)}'

def _ast2tex_intg (ast):
	if ast.from_ is None:
		return \
				f'\\int \\ {ast2tex (ast.dv)}' \
				if ast.intg is None else \
				f'\\int {_ast2tex_wrap (ast.intg, {"diff"}, {"=", "lamb"})} \\ {ast2tex (ast.dv)}'
	else:
		return \
				f'\\int_{_ast2tex_curly (ast.from_)}^{_ast2tex_curly (ast.to)} \\ {ast2tex (ast.dv)}' \
				if ast.intg is None else \
				f'\\int_{_ast2tex_curly (ast.from_)}^{_ast2tex_curly (ast.to)} {_ast2tex_wrap (ast.intg, {"diff"}, {"=", "lamb"})} \\ {ast2tex (ast.dv)}'

_ast2tex_funcs = {
	'=': lambda ast: f'{_ast2tex_eq_hs (ast, ast.lhs)} {AST.Eq.PY2TEX.get (ast.rel, ast.rel)} {_ast2tex_eq_hs (ast, ast.rhs, False)}',
	'#': _ast2tex_num,
	'@': _ast2tex_var,
	'.': _ast2tex_attr,
	'"': lambda ast: f'\\text{{{repr (ast.str_)}}}',
	',': lambda ast: f'{", ".join (ast2tex (c) for c in ast.commas)}{_trail_comma (ast.commas)}',
	'(': lambda ast: f'\\left({ast2tex (ast.paren)} \\right)',
	'[': lambda ast: f'\\left[{", ".join (ast2tex (b) for b in ast.bracks)} \\right]',
	'|': lambda ast: f'\\left|{ast2tex (ast.abs)} \\right|',
	'-': lambda ast: f'-{_ast2tex_wrap (ast.minus, {"#", "-", "*"}, {"=", "+", "lamb"})}',
	'!': lambda ast: f'{_ast2tex_wrap (ast.fact, {"^"}, (ast.fact.op not in {"#", "@", "(", "|", "!", "^", "vec", "mat"} or ast.fact.is_neg_num))}!',
	'+': lambda ast: ' + '.join (_ast2tex_wrap (n, n.strip_lim_sum ().is_intg and n is not ast.adds [-1], \
			(n.op in ("piece", "lamb") and n is not ast.adds [-1]) or n.op in {'=', 'lamb'}) for n in ast.adds).replace (' + -', ' - '),
	'*': _ast2tex_mul,
	'/': lambda ast: f'\\frac{{{_ast2tex_wrap (ast.numer, 0, (ast.numer.base.is_diff_or_part_solo and ast.numer.exp.remove_curlys ().is_pos_int) if ast.numer.is_pow else ast.numer.is_diff_or_part_solo)}}}{{{ast2tex (ast.denom)}}}',
	'^': _ast2tex_pow,
	'log': _ast2tex_log,
	'sqrt': lambda ast: f'\\sqrt{{{ast2tex (ast.rad.strip_paren_noncomma (1))}}}' if ast.idx is None else f'\\sqrt[{ast2tex (ast.idx)}]{{{ast2tex (ast.rad.strip_paren_noncomma (1))}}}',
	'func': _ast2tex_func,
	'lim': _ast2tex_lim,
	'sum': _ast2tex_sum,
	'diff': _ast2tex_diff,
	'intg': _ast2tex_intg,
	'vec': lambda ast: '\\begin{bmatrix} ' + r' \\ '.join (ast2tex (e) for e in ast.vec) + ' \\end{bmatrix}',
	'mat': lambda ast: '\\begin{bmatrix} ' + r' \\ '.join (' & '.join (ast2tex (e) for e in row) for row in ast.mat) + f'{" " if ast.mat else ""}\\end{{bmatrix}}',
	'piece': lambda ast: '\\begin{cases} ' + r' \\ '.join (f'{ast2tex (p [0])} & \\text{{otherwise}}' if p [1] is True else f'{ast2tex (p [0])} & \\text{{for}}\\: {ast2tex (p [1])}' for p in ast.pieces) + ' \\end{cases}',
	'lamb': lambda ast: f'{ast2tex (ast.vars [0] if len (ast.vars) == 1 else AST ("(", (",", ast.vars)))} \\mapsto {_ast2tex_wrap (ast.lamb, 0, ast.lamb.is_ass or ast.lamb.is_lamb)}',

	'text': lambda ast: ast.tex,
}

#...............................................................................................
def ast2nat (ast): # abstract syntax tree -> simple text
	return _ast2nat_funcs [ast.op] (ast)

def _ast2nat_wrap (obj, curly = None, paren = None):
	s = ast2nat (obj) if isinstance (obj, AST) else str (obj)

	if (obj.op in paren) if isinstance (paren, set) else paren:
		return f'({s})'

	if (obj.op in curly) if isinstance (curly, set) else curly:
		return f'{{{s}}}'

	return s

def _ast2nat_curly (ast, ops = {}):
	return _ast2nat_wrap (ast, ops if ops else (ast.is_div or not ast.is_single_unit or (ast.is_var and ast.var in AST.Var.PY2TEX)))
	# if ops:
	# 	return f'{{{ast2nat (ast)}}}' if ast.op in ops else ast2nat (ast)

	# return f'{{{ast2nat (ast)}}}' if not ast.is_single_unit or (ast.is_var and ast.var in AST.Var.PY2TEX) else ast2nat (ast)

def _ast2nat_paren (ast, ops = {}):
	return _ast2nat_wrap (ast, 0, not (ast.is_paren or (ops and ast.op not in ops)))
	# return ast2nat (ast) if ast.is_paren or (ops and ast.op not in ops) else f'({ast2nat (ast)})'

def _ast2nat_curly_mul_exp (ast, ret_has = False, also = {}):
	if ast.is_mul:
		s, has = _ast2nat_mul (ast, True)
	else:
		s, has = ast2nat (ast), False

	has = has or ((ast.op in also) if isinstance (also, set) else also)
	s   = _ast2nat_wrap (s, has)

	return (s, has) if ret_has else s
	# s = f'{{{s}}}' if has else s

	# return (s, has) if ret_has else s

def _ast2nat_eq_hs (ast, hs, lhs = True):
	return _ast2nat_wrap (hs, 0, (hs.is_ass or (lhs and hs.op in {'piece', 'lamb'})) if ast.is_ass else {'=', 'piece', 'lamb'})

def _ast2nat_mul (ast, ret_has = False):
	t   = []
	p   = None
	has = False

	for n in ast.muls:
		# s = _ast2nat_paren (n)   if n.is_add or (p and _ast_is_neg (n)) or (n.is_piece and n is not ast.muls [-1]) else \
		# 		f'{{{ast2nat (n)}}}' if n.is_piece else \
		# 		ast2nat (n)

		# s = _ast2tex_wrap (n, \
		# 		_ast_is_neg (n) or (n.is_intg and n is not ast.muls [-1]), \
		# 		n.op in {'=', '+', "lamb"} or (n.is_piece and n is not ast.muls [-1]))
		s = _ast2nat_wrap (n, \
				_ast_is_neg (n) or n.is_piece or (n.strip_lim_sum ().is_intg and n is not ast.muls [-1]), \
				n.op in {'=', '+', 'lamb'} or (n.is_piece and n is not ast.muls [-1]))
#				(n.op in {'piece', 'lamb'} and n is not ast.muls [-1]) or n.is_add or (p and _ast_is_neg (n)))

		# if p and (n.op in {'!', '#', 'mat'} or n.is_null_var or p.op in {'lim', 'sum', 'diff', 'intg', 'mat'} or \
		# 		(n.is_pow and n.base.is_pos_num) or (n.op in {'/', 'diff'} and p.op in {'#', '/'}) or _ast_is_neg (n) or \
		# 		(p.is_div and (p.numer.is_diff_or_part_solo or (p.numer.is_pow and p.numer.base.is_diff_or_part_solo)))):
		# 	t.append (f' \\cdot {s}')
		# 	has = True
		if p and (n.op in {'!', '#', 'lim', 'sum', 'intg'} or n.is_null_var or p.op in {'lim', 'sum', 'diff', 'intg'} or \
				(n.is_pow and n.base.is_pos_num) or \
				n.op in {'/', 'diff'} or p.strip_minus ().op in {'/', 'diff'}):
			t.append (f' * {s}')
			has = True

		# elif p and (p.op in {'sqrt'} or \
		# 		p.is_diff_or_part_solo or n.is_diff_or_part_solo or p.is_diff_or_part or n.is_diff_or_part or \
		# 		(p.is_long_var and n.op not in {'(', '['}) or (n.is_long_var and p.op not in {'(', '['})):
		# 	t.append (f'\\ {s}')
		elif p and (p.is_diff_or_part_solo or \
				(n.op not in {'#', '(', '|', '^'} or p.op not in {'#', '(', '|'})):
			t.append (f' {s}')

		# else:
		# 	t.append (f'{"" if not p else " "}{s}')
		else:
			t.append (s)

		p = n

	return (''.join (t), has) if ret_has else ''.join (t)

def _ast2nat_div (ast):
	n, ns = (_ast2nat_wrap (ast.numer, 1), True) if _ast_is_neg (ast.numer) else \
		(_ast2nat_wrap (ast.numer, 0, 1), True) if ((ast.numer.base.is_diff_or_part_solo and ast.numer.exp.remove_curlys ().is_pos_int) if ast.numer.is_pow else ast.numer.is_diff_or_part_solo) else \
		_ast2nat_curly_mul_exp (ast.numer, True, {'=', '+', '/', 'lim', 'sum', 'diff', 'intg', 'piece', 'lamb'})

	d, ds = (_ast2nat_wrap (ast.denom, 1), True) if _ast_is_neg (ast.denom) else _ast2nat_curly_mul_exp (ast.denom, True, {'=', '+', '/', 'lim', 'sum', 'diff', 'intg', 'piece', 'lamb'})
	s     = ns or ds or ast.numer.strip_minus ().op not in {'#', '@', '*'} or ast.denom.strip_minus ().op not in {'#', '@', '*'}

	return f'{n}{" / " if s else "/"}{d}'

def _ast2nat_pow (ast, trighpow = True):
	# b = _ast2tex_curly (ast.base) if ast.base.is_mat else ast2tex (ast.base) # TODO: REMOVE

		# b = _ast2tex_wrap (ast.base, {'mat'}, not (ast.base.op in {'@', '"', '(', '|', 'func', 'mat'} or ast.base.is_pos_num))
		# p = _ast2tex_curly (ast.exp)

		# if ast.base.is_trigh_func_noninv and ast.exp.is_single_unit and trighpow:
		# 	i = len (ast.base.func) + (15 if ast.base.func in {'sech', 'csch'} else 1)

		# 	return f'{b [:i]}^{p}{b [i:]}'

		# return f'{b}^{p}'

	# if ast.base.op in {'@', '(', '|', 'mat'} or ast.base.is_pos_num: # TODO: REMOVE
	# 	return f'{b}^{p}'

	# return f'\\left({b} \\right)^{p}'


	# b = ast2nat (ast.base)
	# p = f'{{{ast2nat (ast.exp)}}}' if ast.exp.strip_minus ().op in {'+', '*', '/', 'lim', 'sum', 'diff', 'intg', 'piece'} else ast2nat (ast.exp)
	b = _ast2nat_wrap (ast.base, 0, not (ast.base.op in {'@', '(', '|', 'mat'} or ast.base.is_pos_num))
	p = _ast2nat_wrap (ast.exp, ast.exp.strip_minus ().op in {'=', '+', '*', '/', 'lim', 'sum', 'diff', 'intg', 'piece', 'lamb'}, {","})

	if ast.base.is_trigh_func_noninv and ast.exp.is_single_unit and trighpow:
		i = len (ast.base.func)

		return f'{b [1 : i + 1]}**{p}{b [i + 1 : -1]}'

	return f'{b}**{p}'

	# if ast.base.op in {'@', '(', '|', 'mat'} or ast.base.is_pos_num:
	# 	return f'{b}**{p}'

	# return f'({b})**{p}'

def _ast2nat_log (ast):
	return \
			f'ln{_ast2nat_paren (ast.log)}' \
			if ast.base is None else \
			f'\\log_{_ast2nat_curly (ast.base)}{_ast2nat_paren (ast.log)}'

def _ast2nat_func (ast):
	if ast.is_trigh_func:
		return f'{ast.func}{_ast2nat_paren (_tuple2ast_func_args (ast.args))}'

	return \
			f'{ast.func}{_ast2nat_paren (_tuple2ast_func_args (ast.args))}' \
			if ast.func in AST.Func.PY or ast.func in _USER_FUNCS else \
			f'${ast.func}{_ast2nat_paren (_tuple2ast_func_args (ast.args))}'

def _ast2nat_lim (ast):
	# s = _ast2nat_wrap (ast.to, {'piece'}) if ast.dir is None else ast2nat (AST ('^', ast [3], AST.Zero)) [:-1] + ast [4]
	s = _ast2nat_wrap (ast.to, {'piece'}) if ast.dir is None else (_ast2nat_pow (AST ('^', ast.to, AST.Zero), trighpow = False) [:-1] + ast.dir)

	return f'\\lim_{{{ast2nat (ast.lvar)} \\to {s}}} {_ast2nat_curly_mul_exp (ast.lim, False, ast.lim.op in {"=", "+", "piece", "lamb"} or ast.lim.is_mul_has_abs)}'

def _ast2nat_sum (ast):
	return f'\\sum_{{{ast2nat (ast.svar)}={_ast2nat_curly (ast.from_, {"piece"})}}}^{_ast2nat_curly (ast.to)} {_ast2nat_curly_mul_exp (ast.sum, False, ast.sum.op in {"=", "+", "piece", "lamb"} or ast.sum.is_mul_has_abs)}' \

def _ast2nat_diff (ast):
	p = 0

	for n in ast.dvs:
		if n.is_var:
			d  = n.diff_or_part_type
			p += 1
		else: # n = ('^', ('@', 'differential'), ('#', 'int'))
			d  = n.base.diff_or_part_type
			p += int (n.exp.num)

	return f'{d.strip () if d else "d"}{"" if p == 1 else f"^{p}"} / {" ".join (ast2nat (n) for n in ast.dvs)} {_ast2nat_paren (ast.diff)}'

def _ast2nat_intg (ast):
	if ast.from_ is None:
		return \
				f'\\int {ast2nat (ast.dv)}' \
				if ast.intg is None else \
				f'\\int {_ast2nat_wrap (ast.intg, ast.intg.op in {"diff", "piece"} or ast.intg.is_mul_has_abs, {"=", "lamb"})} {ast2nat (ast.dv)}'
	else:
		return \
				f'\\int_{_ast2nat_curly (ast.from_)}^{_ast2nat_curly (ast.to)} {ast2nat (ast.dv)}' \
				if ast.intg is None else \
				f'\\int_{_ast2nat_curly (ast.from_)}^{_ast2nat_curly (ast.to)} {_ast2nat_wrap (ast.intg, ast.intg.op in {"diff", "piece"} or ast.intg.is_mul_has_abs, {"=", "lamb"})} {ast2nat (ast.dv)}'

_ast2nat_funcs = {
	'=': lambda ast: f'{_ast2nat_eq_hs (ast, ast.lhs)} {AST.Eq.PY2TEX.get (ast.rel, ast.rel)} {_ast2nat_eq_hs (ast, ast.rhs, False)}',
	'#': lambda ast: ast.num,
	'@': lambda ast: ast.var,
	'.': lambda ast: f'{_ast2nat_paren (ast.obj, {"=", "#", ",", "-", "+", "*", "/", "lim", "sum", "intg", "piece", "lamb"})}.{ast.attr}' \
			if ast.args is None else f'{ast2nat (ast.obj)}.{ast.attr}{_ast2nat_paren (_tuple2ast_func_args (ast.args))}',
	'"': lambda ast: repr (ast.str_),
	',': lambda ast: f'{", ".join (ast2nat (c) for c in ast.commas)}{_trail_comma (ast.commas)}',
	'(': lambda ast: f'({ast2nat (ast.paren)})',
	'[': lambda ast: f'[{", ".join (ast2nat (b) for b in ast.bracks)}]',
	'|': lambda ast: f'{{|{ast2nat (ast.abs)}|}}',
	'-': lambda ast: f'-{_ast2nat_wrap (ast.minus, {"#", "-", "*", "piece"}, {"=", "+", "lamb"})}',
	# '!': lambda ast: f'{_ast2nat_paren (ast.fact)}!' if (ast.fact.op not in {'#', '@', '(', '|', '!', '^', 'vec', 'mat'} or ast.fact.is_neg_num) else f'{ast2nat (ast.fact)}!',
	'!': lambda ast: f'{_ast2nat_wrap (ast.fact, {"^"}, ast.fact.op not in {"#", "@", "(", "|", "!", "^", "vec", "mat"} or ast.fact.is_neg_num)}!',
	'+': lambda ast: ' + '.join (_ast2nat_wrap (n, n.op in {'intg', 'piece'} or (n.strip_lim_sum ().is_intg and n is not ast.adds [-1]), \
			(n.op in ('piece', 'lamb') and n is not ast.adds [-1]) or n.op in {'=', 'lamb'}) for n in ast.adds).replace (' + -', ' - '),
	'*': _ast2nat_mul,
	'/': _ast2nat_div,
	'^': _ast2nat_pow,
	'log': _ast2nat_log,
	# 'sqrt': lambda ast: f'sqrt{_ast2nat_paren (ast.rad)}' if ast.idx is None else f'\\sqrt[{ast2nat (ast.idx)}]{{{ast2nat (ast.rad.strip_paren (1))}}}',
	'sqrt': lambda ast: f'sqrt{_ast2nat_paren (ast.rad)}' if ast.idx is None else f'\\sqrt[{ast2tex (ast.idx)}]{{{ast2tex (ast.rad.strip_paren_noncomma (1))}}}',
	'func': _ast2nat_func,
	'lim': _ast2nat_lim,
	'sum': _ast2nat_sum,
	'diff': _ast2nat_diff,
	'intg': _ast2nat_intg,
	'vec': lambda ast: f'{{{", ".join (ast2nat (e) for e in ast.vec)}{_trail_comma (ast.vec)}}}',
	'mat': lambda ast: ('{' + ', '.join (f'{{{", ".join (ast2nat (e) for e in row)}{_trail_comma (row)}}}' for row in ast.mat) + f'{_trail_comma (ast.mat)}}}') if ast.mat else 'Matrix([])',
	'piece': lambda ast: ' else '.join (f'{_ast2nat_curly (p [0], {"=", "piece", "lamb"})}' if p [1] is True else f'{_ast2nat_curly (p [0], {"=", "piece", "lamb"})} if {_ast2nat_curly (p [1], {"piece", "lamb"})}' for p in ast.pieces),
	'lamb': lambda ast: f'lambda{" " + ", ".join (v.var for v in ast.vars) if ast.vars else ""}: {_ast2nat_wrap (ast.lamb, 0, {"=", "lamb"})}',

	'text': lambda ast: ast.nat,
}

#...............................................................................................
def ast2py (ast): # abstract syntax tree -> Python code text
	return _ast2py_funcs [ast.op] (ast)

def _ast2py_curly (ast):
	return \
			_ast2py_paren (ast) \
			if ast.strip_minus ().op in {'+', '*', '/'} or (ast.is_log and ast.base is not None) else \
			ast2py (ast)

def _ast2py_paren (ast):
	return ast2py (ast) if ast.is_paren else f'({ast2py (ast)})'

def _ast2py_div (ast):
	n = _ast2py_curly (ast.numer)
	d = _ast2py_curly (ast.denom)

	return f'{n}{" / " if ast.numer.strip_minus ().op not in {"#", "@"} or ast.denom.strip_minus ().op not in {"#", "@"} else "/"}{d}'

def _ast2py_pow (ast):
	b = _ast2py_paren (ast.base) if _ast_is_neg (ast.base) else _ast2py_curly (ast.base)
	e = _ast2py_curly (ast.exp)

	return f'{b}**{e}'

def _ast2py_log (ast):
	return \
			f'log{_ast2py_paren (ast.log)}' \
			if ast.base is None else \
			f'log{_ast2py_paren (ast.log)} / log{_ast2py_paren (ast.base)}' \

def _ast2py_lim (ast):
	return \
		f'''Limit({ast2py (ast.lim)}, {ast2py (ast.lvar)}, {ast2py (ast.to)}''' \
		f'''{", dir='+-'" if ast.dir is None else ", dir='-'" if ast.dir == '-' else ""})'''

def _ast2py_diff (ast):
	args = sum ((
			(ast2py (n.as_var),) \
			if n.is_var else \
			(ast2py (n.base.as_var), str (n.exp.num)) \
			for n in ast.dvs \
			), ())

	return f'Derivative({ast2py (ast.diff)}, {", ".join (args)})'

def _ast2py_intg (ast):
	if ast.from_ is None:
		return \
				f'Integral(1, {ast2py (ast.dv.as_var)})' \
				if ast.intg is None else \
				f'Integral({ast2py (ast.intg)}, {ast2py (ast.dv.as_var)})'
	else:
		return \
				f'Integral(1, ({ast2py (ast.dv.as_var)}, {ast2py (ast.from_)}, {ast2py (ast.to)}))' \
				if ast.intg is None else \
				f'Integral({ast2py (ast.intg)}, ({ast2py (ast.dv.as_var)}, {ast2py (ast.from_)}, {ast2py (ast.to)}))'

_ast2py_funcs = {
	'=': lambda ast: f'{_ast2py_paren (ast.lhs) if (ast.is_eq and ast.lhs.is_lamb) else ast2py (ast.lhs)} {ast.rel} {ast2py (ast.rhs)}',
	'#': lambda ast: ast.num,
	'@': lambda ast: ast.var,
	'.': lambda ast: f'{ast2py (ast.obj)}.{ast.attr}' if ast.args is None else f'{ast2py (ast.obj)}.{ast.attr}{_ast2py_paren (_tuple2ast_func_args (ast.args))}',
	'"': lambda ast: repr (ast.str_),
	',': lambda ast: f'{", ".join (ast2py (parm) for parm in ast.commas)}{_trail_comma (ast.commas)}',
	'(': lambda ast: f'({ast2py (ast.paren)})',
	'[': lambda ast: f'[{", ".join (ast2py (b) for b in ast.bracks)}]',
	'|': lambda ast: f'abs({ast2py (ast.abs)})',
	'-': lambda ast: f'-{_ast2py_paren (ast.minus)}' if ast.minus.is_add else f'-{ast2py (ast.minus)}',
	'!': lambda ast: f'factorial({ast2py (ast.fact)})',
	'+': lambda ast: ' + '.join (ast2py (n) for n in ast.adds).replace (' + -', ' - '),
	'*': lambda ast: '*'.join (_ast2py_paren (n) if n.is_add else ast2py (n) for n in ast.muls),
	'/': _ast2py_div,
	'^': _ast2py_pow,
	'log': _ast2py_log,
	'sqrt': lambda ast: f'sqrt{_ast2py_paren (ast.rad)}' if ast.idx is None else ast2py (AST ('^', ast.rad.strip_paren (1), ('/', AST.One, ast.idx))),
	'func': lambda ast: f'{ast.func}{_ast2py_paren (_tuple2ast_func_args (ast.args))}',
	'lim': _ast2py_lim,
	'sum': lambda ast: f'Sum({ast2py (ast.sum)}, ({ast2py (ast.svar)}, {ast2py (ast.from_)}, {ast2py (ast.to)}))',
	'diff': _ast2py_diff,
	'intg': _ast2py_intg,
	'vec': lambda ast: 'Matrix([' + ', '.join (f'[{ast2py (e)}]' for e in ast.vec) + '])',
	'mat': lambda ast: 'Matrix([' + ', '.join (f'[{", ".join (ast2py (e) for e in row)}]' for row in ast.mat) + '])',
	'piece': lambda ast: 'Piecewise(' + ', '.join (f'({ast2py (p [0])}, {True if p [1] is True else ast2py (p [1])})' for p in ast.pieces) + ')',
	'lamb': lambda ast: f'lambda{" " + ", ".join (v.var for v in ast.vars) if ast.vars else ""}: {ast2nat (ast.lamb)}',

	'text': lambda ast: ast.py,
}

#...............................................................................................
def ast2spt (ast, doit = False): # abstract syntax tree -> sympy tree (expression)
	spt = _ast2spt_funcs [ast.op] (ast)

	if doit and callable (getattr (spt, 'doit', None)): # and spt.__class__ != sp.Piecewise
		try:
			spt = spt.doit ()
			spt = sp.piecewise_fold (spt) # prevent SymPy infinite piecewise recursion
		except TypeError:
			pass

	return spt

def _ast2spt_attr (ast):
	mbr = getattr (ast2spt (ast.obj), ast.attr)

	return mbr if ast.args is None else _ast_func_call (mbr, ast.args)

# Potentially bad __builtins__: eval, exec, globals, locals, vars, hasattr, getattr, setattr, delattr, exit, help, input, license, open, quit, __import__
_builtins_dict               = __builtins__ if isinstance (__builtins__, dict) else __builtins__.__dict__ # __builtins__.__dict__ if __name__ == '__main__' else __builtins__
_ast2spt_func_builtins_names = ['abs', 'all', 'any', 'ascii', 'bin', 'callable', 'chr', 'dir', 'divmod', 'format', 'hash', 'hex', 'id',
		'isinstance', 'issubclass', 'iter', 'len', 'max', 'min', 'next', 'oct', 'ord', 'pow', 'print', 'repr', 'round', 'sorted', 'sum', 'bool',
		'bytearray', 'bytes', 'complex', 'dict', 'enumerate', 'filter', 'float', 'frozenset', 'property', 'int', 'list', 'map', 'object', 'range',
		'reversed', 'set', 'slice', 'str', 'tuple', 'type', 'zip']

_ast2spt_func_builtins       = dict (no for no in filter (lambda no: no [1], ((n, _builtins_dict.get (n)) for n in _ast2spt_func_builtins_names)))

def _ast2spt_func (ast):
	if ast.func == '@': # special reference meta-function
		return ast2spt (ast.args [0])
	if ast.func == '#': # special stop evaluation meta-function
		return ExprDontDoIt (ast2spt (ast.args [0]))

	func = getattr (sp, ast.func, _ast2spt_func_builtins.get (ast.func))

	if func is None:
		raise NameError (f'function {ast.func!r} is not defined')

	return _ast_func_call (func, ast.args)

def _ast2spt_diff (ast):
	args = sum ((
			(ast2spt (n.as_var),) \
			if n.is_var else \
			(ast2spt (n.base.as_var), sp.Integer (n.exp.num)) \
			for n in ast.dvs \
			), ())

	return sp.Derivative (ast2spt (ast [1]), *args)

def _ast2spt_intg (ast):
	if ast.from_ is None:
		return \
				sp.Integral (1, ast2spt (ast.dv.as_var)) \
				if ast.intg is None else \
				sp.Integral (ast2spt (ast.intg), ast2spt (ast.dv.as_var))
	else:
		return \
				sp.Integral (1, (ast2spt (ast.dv.as_var), ast2spt (ast.from_), ast2spt (ast.to))) \
				if ast.intg is None else \
				sp.Integral (ast2spt (ast [1]), (ast2spt (ast.dv.as_var), ast2spt (ast.from_), ast2spt (ast.to)))

_ast2spt_eq = {
	'=':  sp.Eq,
	'==': sp.Eq,
	'!=': sp.Ne,
	'<':  sp.Lt,
	'<=': sp.Le,
	'>':  sp.Gt,
	'>=': sp.Ge,
}

_ast2spt_consts = { # 'e' and 'i' dynamically set on use from AST.E or I
	'pi'   : sp.pi,
	'oo'   : sp.oo,
	'zoo'  : sp.zoo,
	'None' : None,
	'True' : sp.boolalg.true,
	'False': sp.boolalg.false,
	'nan'  : sp.nan,
}

_ast2spt_funcs = {
	'=': lambda ast: _ast2spt_eq [ast.rel] (ast2spt (ast.lhs), ast2spt (ast.rhs)),
	'#': lambda ast: sp.Integer (ast [1]) if ast.is_int_text (ast.num) else sp.Float (ast.num, _SYMPY_FLOAT_PRECISION),
	'@': lambda ast: {**_ast2spt_consts, AST.E.var: sp.E, AST.I.var: sp.I}.get (ast.var, getattr (sp, ast.var, sp.Symbol (ast.var)) if len (ast.var) > 1 else sp.Symbol (ast.var)),
	'.': _ast2spt_attr,
	'"': lambda ast: ast.str_,
	',': lambda ast: tuple (ast2spt (p) for p in ast.commas),
	'(': lambda ast: ast2spt (ast.paren),
	'[': lambda ast: [ast2spt (b) for b in ast.bracks],
	'|': lambda ast: sp.Abs (ast2spt (ast.abs)),
	'-': lambda ast: -ast2spt (ast.minus),
	'!': lambda ast: sp.factorial (ast2spt (ast.fact)),
	'+': lambda ast: sp.Add (*(ast2spt (n) for n in ast.adds)),
	'*': lambda ast: sp.Mul (*(ast2spt (n) for n in ast.muls)),
	'/': lambda ast: sp.Mul (ast2spt (ast.numer), sp.Pow (ast2spt (ast.denom), -1)),
	'^': lambda ast: sp.Pow (ast2spt (ast.base), ast2spt (ast.exp)),
	'log': lambda ast: sp.log (ast2spt (ast.log)) if ast.base is None else sp.log (ast2spt (ast.log), ast2spt (ast.base)),
	'sqrt': lambda ast: sp.Pow (ast2spt (ast.rad), sp.Pow (2, -1)) if ast.idx is None else sp.Pow (ast2spt (ast.rad), sp.Pow (ast2spt (ast.idx), -1)),
	'func': _ast2spt_func,
	'lim': lambda ast: (sp.Limit if ast.dir else sp.limit) (ast2spt (ast.lim), ast2spt (ast.lvar), ast2spt (ast.to), dir = ast.dir or '+-'),
	'sum': lambda ast: sp.Sum (ast2spt (ast.sum), (ast2spt (ast.svar), ast2spt (ast.from_), ast2spt (ast.to))),
	'diff': _ast2spt_diff,
	'intg': _ast2spt_intg,
	'vec': lambda ast: sp.Matrix ([[ast2spt (e)] for e in ast.vec]),
	'mat': lambda ast: sp.Matrix ([[ast2spt (e) for e in row] for row in ast.mat]),
	'piece': lambda ast: sp.Piecewise (*tuple ((ast2spt (p [0]), True if p [1] is True else ast2spt (p [1])) for p in ast.pieces)),
	'lamb': lambda ast: sp.Lambda (tuple (ast2spt (v) for v in ast.vars), ast2spt (ast.lamb)),
}

#...............................................................................................
def spt2ast (spt): # sympy tree (expression) -> abstract syntax tree
	for cls in spt.__class__.__mro__:
		func = _spt2ast_funcs.get (cls)

		if func:
			return func (spt)

		if cls is sp.Function:
			if len (spt.args) == 1:
				return _spt2ast_Function1 (spt)

			break

	tex = sp.latex (spt)

	if tex [0] == '<' and tex [-1] == '>': # for Python repr style of objects <class something>
		tex = '\\text{' + tex.replace ("<", "&lt;").replace (">", "&gt;").replace ("\n", "") + '}'

	return AST_Text (tex, str (spt), str (spt))

_rec_num_deconstructed = re.compile (r'^(-?)(\d*[^0.e])?(0*)(?:(\.)(0*)(\d*[^0e])?(0*))?(?:([eE])([+-]?\d+))?$') # -101000.000101000e+123 -> (-) (101) (000) (.) (000) (101) (000) (e) (+123)

def _spt2ast_num (spt):
	m = _rec_num_deconstructed.match (str (spt))
	g = [g or '' for g in m.groups ()]

	if g [5]:
		return AST ('#', ''.join (g [:6] + g [7:]))

	e = len (g [2]) + (int (g [8]) if g [8] else 0)

	return AST ('#', \
			f'{g [0]}{g [1]}e+{e}'     if e >= 16 else \
			f'{g [0]}{g [1]}{"0" * e}' if e >= 0 else \
			f'{g [0]}{g [1]}e{e}')

def _spt2ast_MatrixBase (spt):
	return \
			AST ('mat', tuple (tuple (spt2ast (e) for e in spt [row, :]) for row in range (spt.rows))) \
			if spt.cols > 1 else \
			AST ('vec', tuple (spt2ast (e) for e in spt)) \
			if spt.rows > 1 else \
 			spt2ast (spt [0])

def _spt2ast_Add (spt):
	args = spt._sorted_args

	for arg in args:
		if isinstance (arg, sp.Order):
			break
	else:
		args = args [::-1]

	return AST ('+', tuple (spt2ast (arg) for arg in args))

def _spt2ast_Mul (spt):
	if spt.args [0] == -1:
		return AST ('-', spt2ast (sp.Mul (*spt.args [1:])))

	if spt.args [0].is_negative and isinstance (spt, sp.Number):
		return AST ('-', spt2ast (sp.Mul (-spt.args [0], *spt.args [1:])))

	numer = []
	denom = []

	for arg in spt.args:
		if isinstance (arg, sp.Pow) and arg.args [1].is_negative:
			denom.append (spt2ast (sp.Pow (arg.args [0], -arg.args [1])))
		else:
			numer.append (spt2ast (arg))

	if not denom:
		return AST ('*', tuple (numer)) if len (numer) > 1 else numer [0]

	if not numer:
		return AST ('/', AST.One, AST ('*', tuple (denom)) if len (denom) > 1 else denom [0])

	return AST ('/', AST ('*', tuple (numer)) if len (numer) > 1 else numer [0], \
			AST ('*', tuple (denom)) if len (denom) > 1 else denom [0])

def _spt2ast_Pow (spt):
	if spt.args [1].is_negative:
		return AST ('/', AST.One, spt2ast (sp.Pow (spt.args [0], -spt.args [1])))

	if spt.args [1] == 0.5:
		return AST ('sqrt', spt2ast (spt.args [0]))

	return AST ('^', spt2ast (spt.args [0]), spt2ast (spt.args [1]))

def _spt2ast_MatPow (spt):
	try: # compensate for some MatPow.doit() != mat**pow
		return spt2ast (spt.args [0] ** spt.args [1])
	except:
		return AST ('^', spt2ast (spt.args [0]), spt2ast (spt.args [1]))

def _spt2ast_Function1 (spt):
	return AST ('func', spt.__class__.__name__, (spt2ast (spt.args [0]),)) # TODO: Multiple arguments?!?

def _spt2ast_Integral (spt):
	return \
			AST ('intg', spt2ast (spt.args [0]), AST ('@', f'd{spt2ast (spt.args [1] [0]) [1]}'), spt2ast (spt.args [1] [1]), spt2ast (spt.args [1] [2])) \
			if len (spt.args [1]) == 3 else \
			AST ('intg', spt2ast (spt.args [0]), AST ('@', f'd{spt2ast (spt.args [1] [0]) [1]}'))

_spt2ast_funcs = {
	ExprDontDoIt: lambda spt: AST ('func', '#', (spt2ast (spt.args [0]),)),

	None.__class__: lambda spt: AST.None_,
	True.__class__: lambda spt: AST.True_,
	False.__class__: lambda spt: AST.False_,
	str: lambda spt: AST ('"', spt),
	tuple: lambda spt: AST ('(', (',', tuple (spt2ast (e) for e in spt))),
	list: lambda spt: AST ('[', tuple (spt2ast (e) for e in spt)),
	bool: lambda spt: AST.True_ if spt else AST.False_,
	sp.Tuple: lambda spt: spt2ast (spt.args),

	sp.Integer: _spt2ast_num,
	sp.Float: _spt2ast_num,
	sp.Rational: lambda spt: AST ('/', ('#', str (spt.p)), ('#', str (spt.q))) if spt.p >= 0 else AST ('-', ('/', ('#', str (-spt.p)), ('#', str (spt.q)))),
	sp.matrices.MatrixBase: _spt2ast_MatrixBase,
	sp.numbers.ImaginaryUnit: lambda ast: AST.I,
	sp.numbers.Pi: lambda spt: AST.Pi,
	sp.numbers.Exp1: lambda spt: AST.E,
	sp.numbers.Infinity: lambda spt: AST.Infty,
	sp.numbers.NegativeInfinity: lambda spt: AST ('-', AST.Infty),
	sp.numbers.ComplexInfinity: lambda spt: AST.Infty, # not exactly but whatever
	sp.numbers.NaN: lambda spt: AST.NaN,
	sp.Symbol: lambda spt: AST ('@', spt.name),

	sp.boolalg.BooleanTrue: lambda spt: AST.True_,
	sp.boolalg.BooleanFalse: lambda spt: AST.False_,
	sp.Eq: lambda spt: AST ('=', '=', spt2ast (spt.args [0]), spt2ast (spt.args [1])),
	sp.Ne: lambda spt: AST ('=', '!=', spt2ast (spt.args [0]), spt2ast (spt.args [1])),
	sp.Lt: lambda spt: AST ('=', '<', spt2ast (spt.args [0]), spt2ast (spt.args [1])),
	sp.Le: lambda spt: AST ('=', '<=', spt2ast (spt.args [0]), spt2ast (spt.args [1])),
	sp.Gt: lambda spt: AST ('=', '>', spt2ast (spt.args [0]), spt2ast (spt.args [1])),
	sp.Ge: lambda spt: AST ('=', '>=', spt2ast (spt.args [0]), spt2ast (spt.args [1])),

	sp.fancysets.Complexes: lambda spt: AST.Complexes,

	sp.Add: _spt2ast_Add,
	sp.Mul: _spt2ast_Mul,
	sp.Pow: _spt2ast_Pow,
	sp.MatPow: _spt2ast_MatPow,

	sp.Abs: lambda spt: AST ('|', spt2ast (spt.args [0])),
	sp.arg: lambda spt: AST ('func', 'arg', (spt2ast (spt.args [0]),)),
	sp.exp: lambda spt: AST ('^', AST.E, spt2ast (spt.args [0])),
	sp.factorial: lambda spt: AST ('!', spt2ast (spt.args [0])),
	sp.Function: _spt2ast_Function1,
	sp.functions.elementary.trigonometric.TrigonometricFunction: _spt2ast_Function1,
	sp.functions.elementary.hyperbolic.HyperbolicFunction: _spt2ast_Function1,
	sp.functions.elementary.trigonometric.InverseTrigonometricFunction: _spt2ast_Function1,
	sp.functions.elementary.hyperbolic.InverseHyperbolicFunction: _spt2ast_Function1,
	sp.log: lambda spt: AST ('log', spt2ast (spt.args [0])) if len (spt.args) == 1 else AST ('log', spt2ast (spt.args [0]), spt2ast (spt.args [1])),
	sp.Min: lambda spt: AST ('func', 'Min', ((spt2ast (spt.args [0]) if len (spt.args) == 1 else spt2ast (spt.args)),)),
	sp.Max: lambda spt: AST ('func', 'Max', ((spt2ast (spt.args [0]) if len (spt.args) == 1 else spt2ast (spt.args)),)),

	sp.Sum: lambda spt: AST ('sum', spt2ast (spt.args [0]), spt2ast (spt.args [1] [0]), spt2ast (spt.args [1] [1]), spt2ast (spt.args [1] [2])),
	sp.Integral: _spt2ast_Integral,

	sp.Order: lambda spt: AST ('func', 'O', ((spt2ast (spt.args [0]) if spt.args [1] [1] == 0 else spt2ast (spt.args)),)),
	sp.Piecewise: lambda spt: AST ('piece', tuple ((spt2ast (t [0]), True if isinstance (t [1], sp.boolalg.BooleanTrue) else spt2ast (t [1])) for t in spt.args)),
	sp.Lambda: lambda spt: AST ('lamb', spt2ast (spt.args [1]), tuple (spt2ast (v) for v in spt.args [0])),
}

#...............................................................................................
def set_precision (ast): # recurse through ast to set sympy float precision according to longest string of digits found
	global _SYMPY_FLOAT_PRECISION

	prec  = 15
	stack = [ast]

	while stack:
		ast = stack.pop ()

		if not isinstance (ast, AST):
			pass # nop
		elif ast.is_num:
			prec = max (prec, len (ast.num)) # will be a little more than number of digits to compensate for falling precision with some calculations
		else:
			stack.extend (ast [1:])

	_SYMPY_FLOAT_PRECISION = prec if prec > 15 else None

def set_user_funcs (user_funcs):
	global _USER_FUNCS

	_USER_FUNCS = user_funcs

class sym: # for single script
	AST_Text       = AST_Text
	set_precision  = set_precision
	set_user_funcs = set_user_funcs
	ast2tex        = ast2tex
	ast2nat        = ast2nat
	ast2py         = ast2py
	ast2spt        = ast2spt
	spt2ast        = spt2ast

# _RUNNING_AS_SINGLE_SCRIPT = False # AUTO_REMOVE_IN_SINGLE_SCRIPT
# if __name__ == '__main__' and not _RUNNING_AS_SINGLE_SCRIPT: ## DEBUG!
# 	ast = AST ('^', ('@', 'x'), ('-', ('/', ('#', '1'), ('#', '1.0'))))
# 	res = ast2nat (ast)
# 	print (res)
