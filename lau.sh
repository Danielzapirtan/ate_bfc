#! /usr/bin/env bash

test -d KindleUnpack || git clone https://github.com/kevinhendricks/KindleUnpack.git
cd KindleUnpack/lib
chmod 0755 kindleunpack.py
echo -n "Introduceti calea catre fisierul awz3: "
read bookpath
echo -n "Introduceti calea catre directorul destinatie: "
read outdir
mkdir -p $outdir ${outdir}1
test -f $bookpath || echo "Input file not found" && false
./kindleunpack.py --epub_version=2 $bookpath ${outdir}1
outfile=$(basename $bookpath|sed -e "s/azw3$/epub/g")
cp -a ${outdir}1/mobi8/$outfile $outdir
cd $outdir
rm -rf ${outdir1}
echo "Savat fisierul epub in $outdir/$outfile"
