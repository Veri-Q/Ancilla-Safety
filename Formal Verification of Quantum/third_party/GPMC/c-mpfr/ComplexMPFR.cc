
#include "mpfr/mpreal.h"
#include "c-mpfr/ComplexMPFR.h"
#include "ComplexMPFR.h"

Complex::Complex(){
    // mpc_init2(precision);
    // mpc_set_d_d(value, 1, 0, MPC_RNDNN);
    real = mpfr::mpreal(1);
    imag = mpfr::mpreal(0);
}
Complex::Complex(double re){
    // mpc_init2(precision);
    // mpc_set_d_d(value, real, 0, MPC_RNDNN);
    real = mpfr::mpreal(re);
    imag = mpfr::mpreal(0);
}
Complex::Complex(mpfr::mpreal re){
    // mpc_init2(precision);
    // mpc_set_d_d(value, real, 0, MPC_RNDNN);
    real = re;
    imag = mpfr::mpreal(0);
}
Complex::Complex(double re, double im){
    // mpc_init2(precision);
    // mpc_set_d_d(value, real, imag, MPC_RNDNN);
    real = mpfr::mpreal(re);
    imag = mpfr::mpreal(im);
}
Complex::Complex(mpfr::mpreal re, mpfr::mpreal im){
    // mpc_init2(precision);
    // mpc_set_d_d(value, real, imag, MPC_RNDNN);
    real = re;
    imag = im;
}
Complex::~Complex(){
    // mpc_clear(value);
}

void Complex::set_precision(int precision){
    // precision = precision_;
    mpfr::mpreal::set_default_prec(precision);
}
int Complex::get_precision(){
    return mpfr::mpreal::get_default_prec();
}

Complex &Complex::operator=(const int v)
{
    // mpc_set_d_d(value, v, 0, MPC_RNDNN);
    // return *this;
    this->real = mpfr::mpreal(v);
    this->imag = mpfr::mpreal(0);
    return *this;
}

Complex &Complex::operator=(const std::string &s)
{
    // mpc_set_str(value, s.c_str(), 0, MPC_RNDNN);
    // return *this;
    this->real = mpfr::mpreal(s);
    this->imag = mpfr::mpreal(0);
    return *this;
}

bool Complex::operator!=(const int v) const
{
    return ((real != mpfr::mpreal(v)) || (imag != mpfr::mpreal(0)));
}

bool Complex::operator!=(const Complex &v) const
{
    return ((real != v.real) || (imag != v.imag));
}

bool Complex::operator==(const int v) const
{
    return ((real == mpfr::mpreal(v)) && (imag == mpfr::mpreal(0)));
}

bool Complex::operator==(const Complex &v) const
{
    return ((real == v.real) && (imag == v.imag));
}


Complex Complex::operator+(const Complex &v) const
{
    return Complex(real + v.real, imag + v.imag);
}

Complex &Complex::operator+=(const Complex &v)
{
    this->real = real + v.real;
    this->imag = imag + v.imag;
    return *this;
}

Complex Complex::operator*(const Complex &v) const
{
    return Complex(real * v.real - imag * v.imag, real * v.imag + imag * v.real);
}
Complex &Complex::operator*=(const Complex &v)
{
    mpfr::mpreal re = real * v.real - imag * v.imag;
    mpfr::mpreal im = real * v.imag + imag * v.real;
    this->real = re;
    this->imag = im;
    return *this;
}

Complex Complex::operator<<(const int u)
{
    return Complex(real << u, imag << u);
}

Complex Complex::operator<<(const int u) const
{
    return Complex(real << u, imag << u);
}

std::ostream &operator<<(std::ostream &os, Complex const &c)
{
    if (c.imag < 0){
        return os << c.real << c.imag << "i" << std::endl;
    }
    else if (c.imag == 0){
        return os << c.real <<"+" << 0 <<"i"<< std::endl;
    }
    else{
        return os << c.real <<"+" << c.imag <<"i" << std::endl;
    }
}