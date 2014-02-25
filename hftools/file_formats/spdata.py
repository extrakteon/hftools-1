# -*- coding: ISO-8859-1 -*-
#-----------------------------------------------------------------------------
# Copyright (c) 2014, HFTools Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#-----------------------------------------------------------------------------

u"""
SP-Data
=======

    .. autofunction:: read_spdata
    .. autofunction:: save_spdata
    .. autofunction:: normalize_names

"""
import re, pdb, sys, os, itertools

import numpy as np
from numpy import array, concatenate, iscomplexobj

from hftools.dataset import DataDict, DataBlock,  DimSweep, DimRep,\
    DimPartial, hfarray, make_matrix
from hftools.constants import unit_to_multiplier
from hftools.core.exceptions import HFToolsIOError
from hftools.file_formats.common import Comments, db_iterator, make_col_from_matrix,\
    format_complex_header, format_unit_header, format_elem
from hftools.file_formats import merge_blocks
from hftools.file_formats.readbase import ReadFileFormat
from hftools.file_formats.readbase import Stream, Optional, ManyOptional, ManyOptional,\
    One, Token
from hftools.utils import glob, to_numeric


class SPDataIOError(HFToolsIOError):
    pass

reg_num_unit = re.compile(r"^[ \t]*([-0-9.eE]+) ?([dcmunpfakMGTPE]?[A-Za-z/]+)$")
"""
def match_numunit(x):
    res = reg_num_unit.match(x)
    if res:
        value, unit = res.groups()
        multiplier, baseunit = unit_to_multiplier(unit)
        return float(value)*multiplier, baseunit
    else:
        return x
"""


reg_header = re.compile("^[A-Za-z_]")


class ReadSPFileFormat(ReadFileFormat):
    def tokenize(self, stream):
        """Split stream of lines in sp-data format into
        stream of tagged lines.

        input:
        *stream*    stream of lines in sp-data format

        output:
                    stream of tagged lines
                    (tag, line) where tag is one of
                    "Comment", "Header", and "Data"
        """
        comments = []
        data = []
        header = None
        Nhead = None

        for radidx, rad in enumerate(stream):
            rad = rad.strip()
            lineno = radidx + 1
            if not rad: #skip empty lines
                continue
            elif rad.startswith("!Fullcomments") or rad.startswith("!PROPERTIES"):
                continue
            elif rad.startswith("!END-PROPERTIES"):
                yield Token("ENDPROP", lineno, rad)
            elif rad.startswith("!"): #Comment line with potential information
                yield Token("Comment", lineno, rad[1:])
            elif reg_header.match(rad[0]):
                yield Token("Header", lineno, rad)
            else:
                yield Token("Data", lineno, rad)

    def group_blocks(self, stream):
        """Bunch tagged stream into sub blocks. Each sub block
        containing a measurement data block.
        """
        token, lineno, rad = stream.next()
        running = True
        while running:
            comments = []
            header = []
            data = []
            out = [comments, header, data]
            while token == "Comment":
                comments.append(rad)
                try:
                    token, lineno, rad = stream.next()
                except StopIteration:
                    raise SPDataIOError("File can not end in comments")
            if token == "ENDPROP":
                yield out
                try:
                    token, lineno, rad = stream.next()
                except StopIteration:
                    running = False
                continue
            if token == "Header":
                header.append(rad)
                try:
                    token, lineno, rad = stream.next()
                except StopIteration:
                    raise SPDataIOError("File can not end in header")
            else:
                raise SPDataIOError ("Missing header")
            while running and (token == "Data"):   
                data.append(map(to_numeric, rad.split("\t")))
                try:
                    token, lineno, rad = stream.next()
                except StopIteration:
                    running = False
            yield out
        
    def parse_blocks(self, stream):
        for comments, header, data in stream:
            db = DataBlock()
            db.comments = Comments(comments)
            if header and data:
                header = header[0].strip().split("\t")
                Nhead = len(header)
                #data = array(data)
                if Nhead != len(data[0]):
                    raise SPDataIOError("Different number of header variables from data columns")
                output = DataDict()
                for varname, column in zip(header, zip(*data)):
                    output.setdefault(varname, []).append(column)
                for varname in output:
                    data = output[varname]
                    if len(data) > 1:
                        output[varname] = array(output[varname], order="F").T
                    else:
                        output[varname] = array(output[varname][0])

                freq = DimSweep(header[0], output[header[0]])
                db[header[0]] = freq
                for x in output.keys()[1:]:
                    if output[x].ndim == 1:
                        db[x] = hfarray(output[x], dims=(freq,))
                    else:
                        db[x] = hfarray(output[x], dims=(freq, DimRep("rep", output[x].shape[1]))).squeeze()

            remove = []
            for vname in db.comments.property:
                if vname[:1] == "@":
                    db[vname[1:]] = DimPartial(vname[1:], [float(db.comments.property[vname])], unit=db.comments.property[vname].unit)
                    remove.append(vname)
            for v in remove:
                del db.comments.property[v]
            db.comments.fullcomments = [com for com in db.comments.fullcomments if not com.startswith("@")]
            yield db


def format_sp_block(sweepvars, header, fmts, columns, blockname, comments):
    if comments:
        com_added = False
        if comments.fullcomments and comments.property:
            yield ["!Fullcomments"]
        for comment in comments.fullcomments:
            yield ["!" + comment.lstrip("!")]
        if comments.property:
            pass
            #yield ["!PROPERTIES"]
        for k, v in comments.property.iteritems():
            if v.unit:
                vfmt = "%%(name)s [%%(unit)s]: %%(value)%s"%(v.outputformat[1:],)
            else:
                vfmt = "%%(name)s: %%(value)%s"%(v.outputformat[1:],)
            vname = vfmt%dict(name=k, unit=v.unit, value=v)
            com_added = True
            yield ["!%s"%vname]

        if (not sweepvars) and com_added:
            pass
            #yield ["!END-PROPERTIES"]
        
    for iname, fmt, value in sweepvars:
        yield [("!@%s="+fmt)%(iname, value)]
    header, columns = make_col_from_matrix(header, columns, "%s%s%s")
    outheader = format_complex_header(header, columns, "%s", "Re(%s)", "Im(%s)")

    yield outheader
    fmts = [x.outputformat for x in columns]
    for row in zip(*columns):
        out = []
        for elem, fmt in zip(row, fmts):
            out.extend(format_elem(fmt, elem))
        yield out


def save_spdata(db, filename):
    """Write a Datablock to a sp-format file with name filename.
    """
    if isinstance(filename, (str, unicode)):
        fil = open(filename, "w")
    else:
        fil = filename
    for rad in db_iterator(db, format_sp_block):
        fil.write(u"\t".join(rad))
        fil.write(u"\n")
    
    if isinstance(filename, (str, unicode)):
        fil.close()


def read_spdata(filnamn, make_complex=True, property_to_vars=True,
                guess_unit=True, normalize=True, make_matrix=True,
                merge=True, hyper=False, verbose=True):
    return ReadSPFileFormat.read_file(filnamn, make_complex=make_complex, 
                property_to_vars=property_to_vars, guess_unit=guess_unit,
                normalize=normalize, make_matrix=make_matrix, merge=merge, verbose=verbose, hyper=hyper)


if __name__ == "__main__":
    data = read_spdata("tests/testdata/sp-data/sp_oneport_1_1.txt", merge=False)
    data2 = read_spdata("tests/testdata/sp-data/sp_twoport_1.txt")



