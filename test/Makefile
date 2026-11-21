CXX ?= c++
CXXFLAGS ?= -std=c++17 -O1 -Wall -Wextra -Werror -fsanitize=address,undefined

test: test_rdbus
	./test_rdbus

test_rdbus: test_rdbus.cpp ../esphome/components/panasonic_rd/rdbus.h
	$(CXX) $(CXXFLAGS) -o $@ test_rdbus.cpp

clean:
	rm -f test_rdbus

.PHONY: test clean
