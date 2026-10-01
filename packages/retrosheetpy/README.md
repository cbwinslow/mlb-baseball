# retrosheetpy

Pure-Python Retrosheet file client and lossless record/play parser. It needs no
compiler, no Chadwick programs, no PostgreSQL, and no pandas. Work in progress
(slice A of the `pure-python-retrosheet` change); see `API.md` for the planned
public surface.

## Source and attribution

All data this package reads comes from Retrosheet (https://www.retrosheet.org).
Retrosheet's data-use notice asks that anyone using its data say so. If you
publish anything built on it, include this notice:

> The information used here was obtained free of charge from and is
> copyrighted by Retrosheet. Interested parties may contact Retrosheet at
> "www.retrosheet.org".

This package is independent. Retrosheet does not endorse or sponsor it, and the
package ships no Retrosheet data. The package code is AGPL-3.0-or-later.
Chadwick (GPL-2.0) is used only as a test-time reference program; none of its
code is copied here.
