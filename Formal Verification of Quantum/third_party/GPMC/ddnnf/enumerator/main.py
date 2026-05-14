import sys
import time
import ddnnf

help_msg ='''
Commands: 

> mc
model counting

> next [num]
enumerate the next num models. If "num" is not given, num = 1 as default. 
For example, if you run "next" at first, you will get the first model. 
After that, if you run "next 3", you will get the 2nd, 3rd, and 4th models.  
Each model is output as a list of literals in the original CNF that are true under the model.

> get <num>
output the num-th model, and skip enumerating models before the num-th solution. 
Before this command is performed, the model counting should be done because the 
count result is used for this function. 
You can give a number from 0 to <the number of models>-1 as <num>. 
For example, if you perform "get 123", you will get the 123th model. 
After that, if you run "next", you will get the 124th solution.  

> quit
quit this command line.

> help
display this help message.

'''

filename = sys.argv[1]

nnf = ddnnf.NNF()

start = time.time()
print('Parsing input file...')
nnf.parse(filename)
end = time.time()
print(f'Done. (time: {end-start:.2f} s)')

start = time.time()
print('Restoring d-DNNF for original CNF ...')
nnf.canonicalize()
end = time.time()
print(f'Done. (time: {end-start:.2f} s )')
if len(nnf.deletedVars) > 0:
    print('''
    Warning: 
    Because some vars are deleted by preprocessing in GPMC, the d-DNNF does not contain assignments for the deleted vars.
    This tool can only enumerate partial models for projection vars excluding the deleted vars.
    However, each partial model determines a unique assignment for the deleted vars in the original CNF formula.
    This tool does not provide a function for complementing the assignment for the deleted vars.
    If necessary, please use an external tool together, e.g., by running a SAT solver with the original CNF assuming 
    a partial model provided from this enumerator, you can find a complete model for the original CNF.
    ''')
    print(f'Deleted Vars: {nnf.deletedVars}')

print('Please type a command (see help by command "help")')
enumerator = ddnnf.Enumerator(nnf)

while True:
    try:
        user_input = input('> ')
    except (KeyboardInterrupt, EOFError):
        print('\nExit.')
        break
    else:
        if len(user_input) == 0:
            continue

        command_parts = user_input.split(maxsplit=1)

        if command_parts[0] == "mc":
            start = time.time()
            print(enumerator.countModel())
            end = time.time()
            print(f'Done. (time: {end - start:.2f} s )')
        elif command_parts[0] == "next":
            if len(command_parts) > 1:
                num = int(command_parts[1])
            else:
                num = 1

            for i in range(num):
                if enumerator.next():
                    print(f'v {" ".join([str(i) for i in enumerator.solution if i != None])} 0')
                else:
                    print('No more model')
                    break

        elif command_parts[0] == "get":
            if len(command_parts) == 2:
                if enumerator.get(int(command_parts[1])):
                    print(f'v {" ".join([str(i) for i in enumerator.solution if i != None])} 0')
            else:
                print("Invalid syntax. Usage: get <natural number>")
        elif command_parts[0] == "quit":
            break
        elif command_parts[0] == "help":
            print(help_msg)
        else:
            print("Unknown command.")