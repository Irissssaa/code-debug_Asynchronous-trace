#!/bin/bash

set -e

tarball=$1
if ! test -f "$tarball"; then
  echo "Could not open $tarball"
  exit 1
fi

tardir=$(dirname "$tarball")
tardir=$(cd "$tardir" && pwd)
version=$(basename "$tarball" | sed "s/^gdb-//; s/\.tar\.\(gz\|xz\|bz2\)\$//")
debversion=${version}
tarball="$tardir"/$(basename "$tarball")
dfsg="$tardir/gdb_$debversion.orig.tar.xz"
doc="$tardir/gdb-doc_$version.orig.tar.xz"

dir=`cd $(dirname "$0") && pwd`

temp=$(mktemp -d)
olddir=`pwd`

cd "$temp"
mkdir src
cd src
tar -xf "$tarball"
cd ..

src=src/gdb-$version
dest=gdb-$debversion
destdoc=gdb-doc-$debversion

if ! test -d "$src"; then
  echo "Could not find source directory $src"
  exit 1
fi

if test -z "$dest" || test -e "$dest"; then
  echo "Could not create dest directory $dest"
  exit 1
fi

src=`cd "$src" && pwd`

cp -a "$src" "$dest"
cp -a "$src" "$destdoc"

pushd "$dest" > /dev/null

# All of the gdb manpages are GFDL'd now
rm -f $(find gdb \( -name '*.[1-9]' \))

# Almost all of the texinfo documentation is GFDL.  PSIM's is not, but
# we don't need that manual especially anyway.  Special care must be taken
# with observer.texi, which is necessary for the build process.  Remove
# all pregenerated info files, then replace all texinfo files with dummy
# versions.

rm -f $(find . \( -name \*.info -o -name \*.info-\* \))
rm -f $(find . \( -name \*.chm \))

for f in $(find . \( -name \*.texinfo -o -name \*.texi \)); do
  if test $(basename $f) = observer.texi; then
    sed -ne '/@c This/,/@c any later/p; /@deftype/p' "$src/$f" > $f
    continue
  fi

  echo > "$f"
done

popd > /dev/null

tar --auto-compress -cf "$dfsg" gdb-$debversion

pushd "$destdoc" > /dev/null
rm -f $(find . \( -name \*.chm \))
popd > /dev/null

tar --auto-compress -cf "$doc" gdb-doc-$debversion

# XXX maybe we should install this as an exit handler?
cd "$olddir"
rm -rf $temp
