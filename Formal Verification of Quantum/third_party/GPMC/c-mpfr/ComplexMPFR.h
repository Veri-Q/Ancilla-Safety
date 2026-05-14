#ifndef ComplexMPFR_h
#define ComplexMPFR_h
// #include "mpc.h"
#include "c-mpfr/ComplexMPFR.h"

class Complex {
public:
	// Constructor/Destructor
	//
	Complex();
	Complex(double real);
	Complex(mpfr::mpreal real);
	Complex(double real, double imag);
	Complex(mpfr::mpreal real, mpfr::mpreal imag);
	~Complex();

    // static int precision = 15;
    void set_precision(int precision);
    int get_precision();


    // // Operations
    // // =
    // // +, -, *, /, ++, --, <<, >>
    // // *=, +=, -=, /=,
    // // <, >, ==, <=, >=

    // // =
    Complex& operator=(const int v);
    // Complex& operator=(const char* s);
    Complex& operator=(const std::string& s);
    // template <typename real_t> Complex& operator= (const std::complex<real_t>& z);

    bool operator!=(const int v) const;
    bool operator!=(const Complex& v) const;
    bool operator==(const int v) const;
    bool operator==(const Complex& v) const;

    // // +
    Complex operator+(const Complex& v) const;
    Complex& operator+=(const Complex& v);


    // // *
    Complex operator*(const Complex& v) const;
    Complex& operator*=(const Complex& v);

    // //<< Fast Multiplication by 2^u
    Complex operator<<(const int u);
    Complex operator<<(const int u) const;

    friend std::ostream& operator<<(std::ostream& os, Complex const & c);

    // mpc_t value;
    mpfr::mpreal real; 
    mpfr::mpreal imag;   
};
#endif