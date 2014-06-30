# -*- coding: ISO-8859-1 -*-
#-----------------------------------------------------------------------------
# Copyright (c) 2014, HFTools Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------

u"""
arrayobj
========

.. autofunction:: change_shape


"""
import numpy as np
from numpy import ndarray, array, linspace, arange, newaxis,\
    zeros

from hftools.dataset.dim import DimSweep, DimRep, DimMatrix_i, DimMatrix_j,\
    DimBase, DimAnonymous
from hftools.utils import is_numlike, is_integer, deprecate, isnumber
from hftools.core import HFArrayShapeDimsMismatchError, HFArrayError,\
    DimensionMismatchError
from hftools.py3compat import string_types, integer_types


def get_new_anonymous_dim(dims, *k, **kw):
    if isinstance(dims, hfarray):
        dims = dims.dims
    anon_names = set(int(x.name[4:]) for x in dims
                     if (isinstance(x, DimAnonymous) and
                         x.name.startswith("ANON")))
    anon_names.add(0)
    aname = "ANON%s" % (max(anon_names) + 1)
    return DimAnonymous(aname, *k, **kw)


class Dims(tuple):
    def __contains__(self, value):
        if isinstance(value, string_types):
            value = DimBase(value, 1)  # Dummy dim
        if not isinstance(value, DimBase):
            return False
        for x in self:
            if x.name == value.name and isinstance(x, value.__class__):
                return True
        return False

    def get_matching_dim(self, dim):
        if isinstance(dim, DimBase):
            for x in self:
                if x.name == dim.name and isinstance(x, dim.__class__):
                    return x
        raise KeyError("No dim matching %r" % dim)

    def matching_index(self, value):
        if isinstance(value, DimBase):
            for idx, x in enumerate(self):
                if x.name == value.name and isinstance(x, value.__class__):
                    return idx
        raise KeyError("No dim matching %r" % value)


class DimsList(list):
    def __contains__(self, value):
        if not isinstance(value, DimBase):
            return False
        for x in self:
            if x.name == value.name and isinstance(x, value.__class__):
                return True
        return False

    def get_matching_dim(self, value):
        if isinstance(value, DimBase):
            for x in self:
                if x.name == value.name and isinstance(x, value.__class__):
                    return x
        raise KeyError("No dim matching %r" % value)

    def matching_index(self, value):
        if isinstance(value, DimBase):
            for idx, x in enumerate(self):
                if x.name == value.name and isinstance(x, value.__class__):
                    return idx
        raise KeyError("No dim matching %r" % value)


def dims_union(*a):
    newinfo = DimsList(a[0].dims)
    for B in a[1:]:
        for dim in B.dims:
            if dim not in newinfo:
                newinfo.append(dim)
    newinfo.sort(key=lambda x: x.sortprio)
    return Dims(newinfo)


def change_shape(x, newdims):
    u"""Try to change shape of *x* to use newinfo.
       Bygger om en array sa att den matchar alla Axis objekt i *newinfo*
       listan. Nya dimensioner far langden 1 dvs. understatt repetion av
       arrayen i den dimension.

       Om newinfo innehaller nagon ComplexAxis sa gor vi forst om *x* med
       *make_complex_array*.

    """

    newself = x.view()
    newselfshape = []
    neworder = []
    selfdims = x.dims
    for dim in newdims:
        if dim in x.dims:
            newselfshape.append(x.shape[selfdims.matching_index(dim)])
            neworder.append(selfdims.matching_index(dim))
        else:
            newselfshape.append(1)
    newself = newself.transpose(*neworder)
    newself.shape = tuple(newselfshape)
    newself.dims = Dims(newdims)
    return newself


def make_same_dims_list(a):
    newdims = dims_union(*a)
    return [change_shape(x, newdims) for x in a]


def make_same_dims(A, B):
    u"""Anropas med lista med *Arrays*. Returnerar arrayer som har samma *dims*
    dvs vi har anropat change_shape med en *newinfo* som innehaller unionen
    av de Axis objekt som finns i *dims* av *Arrayerna*.

    """
    if not isinstance(B, _hfarray):
        B = A.__class__(B.view(), dims=A.dims, copy=False)
    return make_same_dims_list((A, B))


def remove_tail(x):
    u"""Collapse all dimensions except first and matrix dimensions"""

    a = np.array(x)
    shape = x.shape
    if ismatrix(x):
        newshape = (shape[0], int(np.multiply.reduce(shape[1:-2])))
        newshape = newshape + shape[-2:]
    else:
        newshape = (shape[0], int(np.multiply.reduce(shape[1:])))
    outa = a.reshape(newshape)
    if isinstance(x, hfarray):
        dim = DimRep("Tail", np.arange(outa.shape[1]))
        dims = (x.dims[0], dim)
        if ismatrix(x):
            dims = dims + x.dims[-2:]
        outa = hfarray(outa, dims=dims, unit=x.unit)
    return outa


def remove_rep(data, newdimname="AllReps"):
    u"""Collapse all DimRep dimensions to single dimension
    """
    order = [(i, dim) for i, dim in enumerate(data.dims)
             if isinstance(dim, DimRep)]
#    pdb.set_trace()

    if order:
        dims = list(zip(*order))[1]

        newdata = data.reorder_dimensions(*(data.dims[:order[0][0]] + dims))
        newdata = hfarray(np.ascontiguousarray(data, dtype=data.dtype),
                          dims=newdata.dims, dtype=newdata.dtype,
                          unit=newdata.unit)
        shapes = [data.shape[i] for i, _ in order]
        repsize = int(np.multiply.reduce(shapes))
        a = np.array(data)
        a.shape = (data.shape[:order[0][0]] + (repsize,) +
                   data.shape[order[-1][0] + 1:])
        dims = (data.dims[:order[0][0]] + (DimRep(newdimname, repsize),) +
                data.dims[order[-1][0] + 1:])
    else:
        dims = data.dims
        a = data
    return data.__class__(a, dims=dims, copy=False)


def ismatrix(a):
    i = False
    j = False
    if isinstance(a, _hfarray):
        for dim in a.dims:
            if isinstance(dim, DimMatrix_i):
                i = True
            elif isinstance(dim, DimMatrix_j):
                j = True
            else:
                pass
            if i and j:
                return True
    return False


def check_instance(func):
    def a(self, other):
        try:
            if self.__array_priority__ < other.__array_priority__:
                return NotImplemented
        except AttributeError:
            pass
        if isnumber(other):
            a, b = self, other
        else:
            a, b = make_same_dims(self, self.__class__(other))
        return func(a, b)
    return a


def replace_dim(dims, olddim, newdim):
    out = []
    for d in dims:
        if olddim.name == d.name:
            out.append(newdim)
        else:
            out.append(d)
    return Dims(out)


class _hfarray(ndarray):
    u"""Basklass som ej skall anvandas direkt
    """
    default_dim = (DimSweep("freq", array(0)), DimRep("rep", array(0)))

    def __new__(subtype, data, dims=None, dtype=None, copy=True, order=None,
                subok=False, ndmin=0, unit=None, outputformat=None, info=None):

        if info is not None:
            deprecate("hfarray, use dims not info")
            if dims is not None:
                raise ValueError("Can not specify both info and dims")
            dims = info

        # Make sure we are working with an array, and copy the data
        # if requested
        subarr = np.array(data, dtype=dtype, copy=copy,
                          order=order, subok=subok,
                          ndmin=ndmin)

        # Transform 'subarr' from an ndarray to our new subclass.
        subarr = subarr.view(subtype)

        # Use the specified 'dims' parameter if given
        if dims is None:
            if hasattr(data, 'dims'):
                dims = tuple(data.dims)
            elif subarr.ndim == 0:
                dims = tuple()
            elif len(subarr.shape) <= len(subtype.default_dim):
                dims = tuple(x.__class__(x.name, range(size))
                             for (x, size) in zip(subtype.default_dim,
                                                  subarr.shape))
            else:
                msg = ("On creation of %s *dims* "
                       "must be specified" % subtype.__name__)
                raise DimensionMismatchError(msg)

        subarr._dims = Dims(dims)
        # Check to see that dims matches shape
        subarr.verify_dimension()
        if outputformat is not None:
            subarr.outputformat = outputformat
        elif hasattr(data, "outputformat"):
            subarr.outputformat = data.outputformat
        else:
            if is_integer(subarr):
                subarr.outputformat = "%d"
            elif is_numlike(subarr):
                subarr.outputformat = "%.16e"
            elif np.issubdtype(subarr.dtype, np.datetime64):
                subarr.outputformat = "%s"
            else:
                subarr.outputformat = "%s"

        # Finally, we must return the newly created object:
        if unit is None and hasattr(data, "unit"):
            subarr.__dict__["unit"] = data.unit
        else:
            subarr.__dict__["unit"] = unit
        return subarr

    @property
    def dims(self):
        return self._dims

    @dims.setter
    def dims(self, value):
        self._dims = Dims(value)

    @property
    def info(self):
        deprecate("hfarray, use dims not info")
        return self.dims

    @info.setter
    def info(self, value):
        deprecate("hfarray, use dims not info")
        self.dims = value

    def __repr__(self):
        prefix = " " * (len(self.__class__.__name__) - 5)
        r = np.asarray(self).__repr__()
        rlist = r.split("\n")
        out = [rlist[0].replace("array", self.__class__.__name__)]

        for rad in rlist[1:]:
            out.append(prefix + rad)
        return "\n".join(out)

    def __array_finalize__(self, obj):
        self.__dict__["_dims"] = Dims(getattr(obj, "_dims", Dims()))
        self.__dict__["outputformat"] = getattr(obj, "outputformat", "%.16e")
        self.__dict__["unit"] = getattr(obj, "unit", None)

    def verify_dimension(self):
        u"""Internal function that checks to see if the arrays dimensions match
           those of the *dims* specification.
        """
        if len(self.dims) != self.ndim:
            raise HFArrayShapeDimsMismatchError

    def dims_index(self, name, cls=None):
        u"""Leta upp index for axisobjekt med *name*
        """
        for idx, ax in enumerate(self.dims):
            if ax.name == name:
                if cls is None:
                    return idx
                elif isinstance(ax, cls):
                    return idx
        msg = "Can not find AxisObject with name:%r and cls:%s" % (name, cls)
        raise IndexError(msg)

    def info_index(self, name, cls=None):
        deprecate("info_index deprecated")
        return self.dims_index(name, cls)

    def replace_dim(self, olddim, newdim):
        if isinstance(olddim, string_types):
            olddim = self.dims_index(olddim)
            olddim = self.dims[olddim]
            if np.issubclass_(newdim, DimBase):
                newdim = newdim(olddim)
        self.dims = replace_dim(self.dims, olddim, newdim)
        return self.dims

    def view(self, dtype=None, type=None):
        u"""Return view of *data* i.e. new *hfarray* object but pointing to
           same data.
        """
        if type is None:
            return self.__class__(ndarray.view(self, dtype=self.dtype),
                                  dims=self.dims, copy=False)
        else:
            return ndarray.view(self, dtype=self.dtype, type=type)

    def reorder_dimensions(self, *order):
        u"""Omorganiserar ordningen pa Axis i *dims*. Genom att flytta Axis
           objekten som raknas upp i *order* till borjan.

        """
        infos = list(self.dims[:])
        neworder = []
        for dim in order:
            neworder.append(self.dims.index(dim))
            del infos[infos.index(dim)]
        for dim in infos:
            neworder.append(self.dims.index(dim))
        return self.transpose(*neworder)

    def transpose(self, *order):
        u"""Returnerar hfarray med dimensionerna omorganiserade i ordning
        som ges av *order*. *order* anger index i *dims* listan.

           .. todo:: Ta aven emot en lista med Axis objekt.
        """
        if not order:
            order = range(self.ndim)[::-1]
        return self.__class__(ndarray.transpose(self, *order),
                              dims=[self.dims[i] for i in order], copy=False)

    @property
    def T(self):
        return self.transpose()

    @property
    def t(self):
        """transpose dimensions indicated by DimMatrix_i and DimMatrix_j

        The position of the dimensions will be kept but the data will be
        transposed.

        The dimensions will be transformed like:
        (..., DimMatrix_i("i", [1, 2, 3]), DimMatrix_j("j", [1, 2]),) =>
        (..., DimMatrix_i("i", [1, 2]), DimMatrix_j("j", [1, 2, 3]),) =>
        """
        di = None
        dj = None
        for dim in self.dims:
            if isinstance(dim, DimMatrix_i):
                di = dim
            elif isinstance(dim, DimMatrix_j):
                dj = dim
        if di is None or dj is None:
            return self
        i = self.dims_index(di)
        j = self.dims_index(dj)
        order = list(range(self.ndim))
        order[i], order[j] = order[j], order[i]
        out = self.transpose(*order)
        newdims = list(out.dims)
        newdims[i], newdims[j], = (DimMatrix_i(di.name, dj.data),
                                   DimMatrix_j(dj.name, di.data))
        out.dims = Dims(newdims)
        return out

    def take(self, indices, axis=None, out=None, mode="raise"):
        if axis is None:
            data = np.ndarray.take(self, indices, axis, out, mode)
            return hfarray(data, dims=(DimAnonymous("anon1", indices), ))
        axis = self.dims_index(axis_handler(self, axis))
        olddim = self.dims[axis]
        newdim = olddim.__class__(olddim.name, indices)
        data = np.ndarray.take(self, indices, axis, out, mode)
        newdims = list(self.dims)
        newdims[axis] = newdim
        data.dims = Dims(newdims)
        return data

    def squeeze(self, axis=None):
        u"""Remove single-dimensional entries from the shape of an array.

        """
        dims, dimidxs = multiple_axis_handler(self, axis)

        if dims is None:
            newinfo = [ax for idx, ax in enumerate(self.dims)
                       if self.shape[idx] != 1]
        else:
            newinfo = [ax for idx, ax in enumerate(self.dims)
                       if idx not in dimidxs]
        return self.__class__(ndarray.squeeze(self, axis=dimidxs),
                              dims=newinfo, copy=False)

    def apply_outputformat(fun):
        def __getitem__(self, *x, **kw):
            out = fun(self, *x, **kw)
            if hasattr(self, "outputformat") and hasattr(out, "outputformat"):
                out.outputformat = self.outputformat
            if hasattr(self, "unit") and hasattr(out, "unit"):
                out.unit = self.unit
            return out
        return __getitem__

    @apply_outputformat
    def __getslice__(self, start, stop):
        return self.__getitem__(slice(start, stop))

    @apply_outputformat
    def __getitem__(self, x):
        if x is newaxis or (isinstance(x, tuple) and newaxis in x):
            return self.view(type=ndarray, dtype=self.dtype)[x]
        if x is Ellipsis:
            return self.view()
        if isinstance(x, tuple):
            indices = x
        else:
            indices = (x,)
        ellipsis_and_ints = True
        orig_indices = indices
        for i in indices:
            if isinstance(i, integer_types) or i is Ellipsis:
                pass
            else:
                ellipsis_and_ints = False

        ellips_count = len([i for i in indices
                            if isinstance(i, type(Ellipsis))])
        if ellips_count == 1:
            i = indices.index(Ellipsis)
            indices = (indices[:i] + (slice(None),) *
                       (self.ndim - (len(x) - 1)) + indices[i + 1:])
        elif ellips_count > 1:
            raise IndexError("Can not handle more than one Ellipsis")

        dims = self.dims
        testbool = (len(indices) == 1 and
                    isinstance(indices[0], hfarray) and
                    indices[0].dtype == bool)
        if testbool:
            reorder = []
            for dim in self.dims:
                if dim not in indices[0].dims:
                    reorder.append(dim)
                else:
                    break
            reorder2 = reorder + list(indices[0].dims)
            reordered = self.reorder_dimensions(*reorder2)
            if len(indices[0].dims) == 1:
                dim = indices[0].dims[0]
                newdim = dim.__class__(dim.name,
                                       np.array(dim.data)[indices[0]],
                                       unit=dim.unit)
            else:
                newdim = get_new_anonymous_dim(self, int(np.sum(indices[0])))

            dims = (reordered.dims[:len(reorder)] +
                    (newdim,) +
                    reordered.dims[len(reorder) + len(indices[0].dims):])
            idx = (slice(None), ) * len(reorder) + (indices[0],)
            return hfarray(ndarray.__getitem__(reordered, idx), dims=dims)

        indices = indices + (slice(None),) * (self.ndim - len(indices))
        dims = []
        dim_in_indices = dict((x.dims[0].name, x.dims[0]) for x in indices
                              if isinstance(x, hfarray))
        for idx, dim in zip(indices, self.dims):
            if isinstance(idx, integer_types):
                continue
            elif isinstance(idx, slice):
                dims.append(dim[idx])
            else:
                dims.append(dim_in_indices.get(dim.name, dim))
        if ellipsis_and_ints:
            indices = orig_indices
        out = ndarray.__getitem__(self, indices)
        if isinstance(out, ndarray):
            return self.__class__(out, dims=dims, copy=False)
        else:
            return out

    @check_instance
    def __and__(self, other):
        q = ndarray.__and__(self, other)
        return q

    @check_instance
    def __or__(self, other):
        q = ndarray.__or__(self, other)
        return q

    @check_instance
    def __xor__(self, other):
        q = ndarray.__xor__(self, other)
        return q

    @check_instance
    def __add__(self, other):
        return ndarray.__add__(self, other)

    @check_instance
    def __sub__(self, other):
        return ndarray.__sub__(self, other)

    @check_instance
    def __mul__(self, other):
        return ndarray.__mul__(self, other)

    @check_instance
    def __div__(self, other):
        return ndarray.__div__(self, other)

    @check_instance
    def __truediv__(self, other):
        return ndarray.__truediv__(self, other)

    @check_instance
    def __pow__(self, other):
        return ndarray.__pow__(self, other)

    @check_instance
    def __rand__(self, other):
        q = ndarray.__rand__(self, other)
        return q

    @check_instance
    def __ror__(self, other):
        q = ndarray.__ror__(self, other)
        return q

    @check_instance
    def __rxor__(self, other):
        q = ndarray.__rxor__(self, other)
        return q

    @check_instance
    def __radd__(self, other):
        return self.__add__(other)

    @check_instance
    def __rsub__(self, other):
        return (-self).__add__(other)

    @check_instance
    def __rmul__(self, other):
        return self.__mul__(other)

    @check_instance
    def __eq__(self, other):
        return ndarray.__eq__(self, other)

    @check_instance
    def __rdiv__(self, other):
        return np.divide(other, self)

    @check_instance
    def __rtruediv__(self, other):
        return np.divide(other, self)

    @check_instance
    def __rpow__(self, other):
        return np.power(other, self)

    def __abs__(self):
        return ndarray.__abs__(self)

    def __neg__(self):
        return ndarray.__neg__(self)

    def copy(self):
        u"""Skapa kopia av objekt
        """
        return self.__class__(self)

    def rss(self, axis=None):
        u"""Berakna kvadratsumma over *axis*. Dar *axis* specas av index till
           *dims*.

           .. todo:: Ta aven emot en lista med Axis objekt.
        """
        return (abs(self) ** 2).sum(axis) ** 0.5

    def sum(self, axis=None, dtype=None, out=None, keepdims=False,
            dimerror=True):
        try:
            dims, dimidx = multiple_axis_handler(self, axis)
        except IndexError:
            if dimerror:
                raise
            else:
                return self
        r = np.asarray(self).sum(dimidx, dtype=dtype, out=out, keepdims=True)
        res = hfarray(r, dims=self.dims)
        if not keepdims:
            res = res.squeeze(axis=dimidx)
        return res

    def mean(self, axis=None, dtype=None, out=None, keepdims=False,
             dimerror=True):
        try:
            dims, dimidx = multiple_axis_handler(self, axis)
        except IndexError:
            if dimerror:
                raise
            else:
                return self
        r = np.asarray(self).mean(dimidx, dtype=dtype, out=out, keepdims=True)
        res = hfarray(r, dims=self.dims)
        if not keepdims:
            res = res.squeeze(axis=dimidx)
        return res

    def std(self, axis=None, dtype=None, out=None, ddof=0, keepdims=False,
            dimerror=True):
        u"""Berakna standardavvikelse over *axis*. Dar *axis* specas av index
           till *dims*.

           .. todo:: Ta aven emot en lista med Axis objekt.
        """
        try:
            dims, dimidx = multiple_axis_handler(self, axis)
        except IndexError:
            if dimerror:
                raise
            else:
                return self
        r = np.asarray(self).std(dimidx, dtype=dtype, out=out, keepdims=True)
        res = hfarray(r, dims=self.dims)
        if not keepdims:
            res = res.squeeze(axis=dimidx)
        return res

    def var(self, axis=None, dtype=None, out=None, ddof=0, keepdims=False,
            dimerror=True):
        u"""Berakna standardavvikelse over *axis*. Dar *axis* specas av index
           till *dims*.

           .. todo:: Ta aven emot en lista med Axis objekt.
        """
        try:
            dims, dimidx = multiple_axis_handler(self, axis)
        except IndexError:
            if dimerror:
                raise
            else:
                return self
        r = np.asarray(self).var(dimidx, dtype=dtype, out=out, keepdims=True)
        res = hfarray(r, dims=self.dims)
        if not keepdims:
            res = res.squeeze(axis=dimidx)
        return res

    def min(self, axis=None, out=None, keepdims=False, dimerror=True):
        u"""Berakna minsta varde over *axis*. Dar *axis* specas av index
           till *dims*.

           .. todo:: Ta aven emot en lista med Axis objekt.
        """
        try:
            dims, dimidx = multiple_axis_handler(self, axis)
        except IndexError:
            if dimerror:
                raise
            else:
                return self
        r = np.asarray(self).min(dimidx, out=out, keepdims=True)
        res = hfarray(r, dims=self.dims)
        if not keepdims:
            res = res.squeeze(axis=dimidx)
        return res

    def max(self, axis=None, out=None, keepdims=False, dimerror=True):
        u"""Berakna storsta varde over *axis*. Dar *axis* specas av index
           till *dims*.

           .. todo:: Ta aven emot en lista med Axis objekt.
        """
        try:
            dims, dimidx = multiple_axis_handler(self, axis)
        except IndexError:
            if dimerror:
                raise
            else:
                return self
        r = np.asarray(self).max(dimidx, out=out, keepdims=True)
        res = hfarray(r, dims=self.dims)
        if not keepdims:
            res = res.squeeze(axis=dimidx)
        return res

    def cumprod(self, axis=0, dtype=None, out=None):
        if axis is None:
            raise HFArrayError("Must choose axis for cumulative product")
        axis = axis_handler(self, axis)
        result = np.asarray(self).cumprod(axis=self.dims_index(axis),
                                          dtype=dtype, out=out)
        return self.__class__(result, dims=self.dims, copy=False)

    def cumsum(self, axis=0, dtype=None, out=None):
        if axis is None:
            raise HFArrayError("Must choose axis for cumulative product")
        axis = axis_handler(self, axis)
        result = np.asarray(self).cumsum(axis=self.dims_index(axis),
                                         dtype=dtype, out=out)
        return self.__class__(result, dims=self.dims, copy=False)

    def help(self):
        out = "\n".join(["class: %(_class)s",
                         "dtype: %(dtype)s",
                         "shape: %(shape)r",
                         "dims:  (%(dims)s)"])
        dims = ["%r" % self.dims[0]]
        for i in self.dims[1:]:
            dims.append("        %r" % i)
        out = out % dict(_class=self.__class__.__name__,
                         dtype=self.dtype,
                         shape=self.shape,
                         dims=",\n".join(dims),
                         )
        return out

    def add_dim(self, dim, axis=0):
        if dim is None:
            return self
        if dim in self.dims:
            return self
        axis = min(axis, self.ndim)
        out = self[(slice(None), ) * axis + (None, )]
        if len(dim.data) > 1:
            out = out.repeat(len(dim.data), axis)
        dims = list(self.dims)
        dims.insert(axis, dim)
        return self.__class__(out, dims=dims, copy=False)


def axis_handler(a, axis):
    if axis is None:
        return None
    elif isinstance(axis, integer_types):
        return a.dims[axis]
    if isinstance(axis, string_types):
        i = a.dims_index(axis)
        axis = a.dims[i]

    if isinstance(axis, type) and issubclass(axis, DimBase):
        outaxis = []
        for dim in a.dims:
            if isinstance(dim, axis):
                outaxis.append(dim)
        if len(outaxis) == 0:
            msg = "%r dimension not present in dims %r"
            msg = msg % (axis.__name__, a.dims)
            raise IndexError(msg)
        elif len(outaxis) == 1:
            return outaxis[0]
        else:
            msg = "There are several %r present in %r"
            msg = msg % (axis, a.dims)
            raise IndexError(msg)
    elif axis in a.dims:
        return axis
    else:
        msg = "%r not a valid dimension for %r"
        raise IndexError(msg % (axis, a.dims))


def multiple_axis_handler(a, axis):
    if axis is None:
        return None, None
    if not isinstance(axis, (tuple, list)):
        axis = [axis]
    outaxis = []
    outidx = []
    for ax in axis:
        if isinstance(ax, integer_types):
            outaxis.append(a.dims[ax])
            outidx.append(ax)
            continue
        if isinstance(ax, string_types):
            i = a.dims_index(ax)
            ax = a.dims[i]
        if isinstance(ax, type) and issubclass(ax, DimBase):
            for dimidx, dim in enumerate(a.dims):
                if isinstance(dim, ax):
                    outaxis.append(dim)
                    outidx.append(dimidx)
        elif isinstance(ax, DimBase) and ax in a.dims:
            outaxis.append(ax)
            outidx.append(a.dims.index(ax))
        else:
            msg = "%r dimension not present in dims %r"
            msg = msg % (ax, a.dims)
            raise IndexError(msg)
    return tuple(outaxis), tuple(outidx)


class hfarray(_hfarray):
    def __new__(subtype, data, dims=None, dtype=None, copy=True, order=None,
                subok=False, ndmin=0, unit=None, outputformat=None, info=None):
        if hasattr(data, "__hfarray__"):
            data, dims = data.__hfarray__()
            if unit is None and len(dims) == 1:
                unit = dims[0].unit
            if outputformat is None and len(dims) == 1:
                outputformat = dims[0].outputformat
        return _hfarray.__new__(subtype, data, dims=dims, dtype=dtype,
                                copy=copy, order=order, subok=subok,
                                ndmin=ndmin, unit=unit,
                                outputformat=outputformat, info=info)


class ValueArray(hfarray):
    """This class is included, for compatibility reasons.
    Do not use in new code."""
    pass


def make_matrix(data, dims, iname="i", jname="j"):
    dims = dims + (DimMatrix_i(iname, arange(data.shape[-2])),
                   DimMatrix_j(jname, arange(data.shape[-1])))
    return hfarray(data, dims, copy=False)


def make_vector(data, dims, jname="j"):
    dims = dims + (DimMatrix_j(jname, arange(data.shape[-1])),)
    return hfarray(data, dims, copy=False)


if __name__ == '__main__':
    fi = DimSweep("freq", linspace(0, 10e9, 11))
    ri = DimRep("rep", range(10))
    a = hfarray(zeros((11, 10)), (fi, ri))
    b = hfarray(zeros((11, )), (fi, ))
    c = hfarray(zeros((10, )), (ri, ))
