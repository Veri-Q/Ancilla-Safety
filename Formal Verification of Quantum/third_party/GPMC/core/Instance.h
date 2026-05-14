#ifndef Instance_h
#define Instance_h

#include <vector>
#include "core/SolverTypes.h"

#include <gmpxx.h>
#include "mpfr/mpreal.h"

namespace GPMC {

// values for variable map
const Glucose::Var var_Determined = {-2};

template <class T_data>
class Instance {
public:
	Instance();

	void set_gweight(std::vector<std::string> tokens);
	void set_lit_weights(std::vector<std::string> tokens);
	void load			(std::istream& in, bool weighted, bool projected, bool ddnnf);
	bool addClause	(std::vector<Glucose::Lit>& lits, bool learnt=false);

	Glucose::lbool value (Glucose::Var x) const;
	Glucose::lbool value (Glucose::Lit p) const;

	// variable correspondence
	void printVarMapStats() const;
	void writeVarMap(std::ostream& out);

	// import extra var score
	void importVarScore(std::istream& in);

	// For Debug
	void toDimacs(std::ostream& out);

	// CNF formula
	int vars;
	std::vector<std::vector<Glucose::Lit>> clauses;
	std::vector<std::vector<Glucose::Lit>> learnts;

	// Counter Mode
	bool weighted;
	bool projected;

	// For WMC/WPMC
	std::vector<T_data> lit_weights;

	// For PMC/WPMC
	int npvars;
	std::vector<bool> ispvars;
	std::vector<Glucose::Var> pvars;

	// Instance keeps temporal fixed literals. Preprocessor will eliminate fixed variables.
	std::vector<Glucose::lbool>	assigns;
	std::vector<Glucose::Lit>	assignedLits;

	// additional information
	int freevars;
	T_data gweight;

	// information about correspondence with a given CNF
	bool keepVarMap;
	std::vector<Glucose::Lit> gmap;								// variable renaming (original (Var) -> simplified (Lit))
	std::vector<Glucose::Lit> fixedLits;						// fixed Literals
	std::vector<Glucose::Var> definedVars;						// variables defined by the other variables
	std::vector<std::vector<Glucose::Lit>> freeLitClasses;	// equivalence classes of free literals

	// extra var score
	std::vector<double> score;

	// State
	bool unsat;

};

template <class T_data>
inline Glucose::lbool Instance<T_data>::value (Glucose::Var x) const { return assigns[x]; }
template <class T_data>
inline Glucose::lbool Instance<T_data>::value (Glucose::Lit p) const { return assigns[var(p)] ^ sign(p); }

}

#endif
