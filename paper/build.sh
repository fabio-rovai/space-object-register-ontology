#!/bin/sh
# Build the paper. Tectonic resolves packages on demand and runs bibtex itself.
set -e
cd "$(dirname "$0")"
tectonic -X compile main.tex --keep-intermediates --synctex
