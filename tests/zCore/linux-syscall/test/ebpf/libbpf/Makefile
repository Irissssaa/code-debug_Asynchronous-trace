

LIB=-L/home/lbr/local/usr/lib64/
INC=-I/home/lbr/local/usr/include/

default: kern.o

kern.o: kern.c
	clang-12 $(LIB) $(INC) -target bpf -g -O1 -c -o $@ $<


