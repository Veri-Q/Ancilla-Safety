from enum import Enum

class NodeType(Enum):
    '''
        The type of nodes in d-DNNF
    '''
    LIT = 0     # literal
    OR  = 1     # or
    AND = 2     # and
    BOT = 3     # bottom
    TOP = 4     # bottom

class Branch(Enum):
    LEFT  = 0
    RIGHT = 1

class Node(object):
    '''
        d-DNNF node class
    '''
    def __init__(self, type, lit = None, children = None):
        '''
            arguments
                type : node type
                lit  : literal for Lit node)
                children : child nodes for OR/AND node)
        '''
        self.type = type
        if type == NodeType.LIT:
            self.lit = lit
        else:
            self.children = children

        self.choice = None      # The current choice (0: left, 1:right): node state for enumeration
        self.count  = None      # To cache the number of solutions for the sub nnf rooted by the current

    def reset(self, reset_count=True):
        self.choice = None
        if reset_count:
            self.count  = None

    def countModels(self):
        if self.count != None:
            return self.count

        if self.type == NodeType.LIT:
            self.count = 1
        elif self.type == NodeType.OR:
            self.count = self.children[0].countModels() + self.children[1].countModels()
        elif self.type == NodeType.AND:
            self.count = 1
            for child in self.children:
                self.count *= child.countModels()
        else:
            print("Error: illegal node")

        return self.count

class NNF(object):
    '''
        NNF class
    '''
    def __init__(self):
        self.root           = None
        self.nodepool       = []
        self.fixedLits      = []
        self.freeVarGroups  = []
        self.deletedVars    = []
        self.map            = {}

        self.nvars          = 0
        isCanonicalized     = False

    def addNode(self, type, child_idxes = None, lit = None):
        if child_idxes != None:
            cnodes = []
            for child_idx in child_idxes:
                cnodes.append(self.nodepool[child_idx])
            self.nodepool.append(Node(type, children = cnodes))
        else:
            self.nodepool.append(Node(type, lit = lit))

    def parse(self, filename):
        self.nodepool = []
        with open(filename) as f:
            for line in f:
                line_block = line.split()
                head_symb  = line_block[0]

                if head_symb == 'v':
                    simplit = int(line_block[2])
                    simpvar = abs(simplit)

                    origvar = int(line_block[1])
                    origlit = origvar if simplit > 0 else -1*origvar

                    if simpvar in self.map:
                        self.map.get(simpvar).append(origlit)
                    else:
                        self.map[simpvar] = [origlit]
                elif head_symb == 'O':
                    self.addNode(NodeType.OR,  child_idxes = list(map(int,line_block[3:])))
                elif head_symb == 'A':
                    self.addNode(NodeType.AND, child_idxes = list(map(int,line_block[2:])))
                elif head_symb == 'L':
                    self.addNode(NodeType.LIT, lit = int(line_block[1]))
                elif head_symb == 'a':
                    self.fixedLits = list(map(int, line_block[1:-1]))
                elif head_symb == 'd':
                    self.deletedVars = list(map(int, line_block[1:-1]))
                elif head_symb == 'f':
                    self.freeVarGroups.append(list(map(int, line_block[1:-1])))
                elif head_symb == 'p':
                    self.nvars = int(line_block[2])

        if len(self.nodepool) > 0:
            self.root = self.nodepool[-1]

    def reset(self, reset_count=True):
        for node in self.nodepool:
            node.reset(reset_count)

    def __replace(self, node):
        if node.count != None:
            return

        if node.type == NodeType.OR or node.type == NodeType.AND:
            newchildren = []
            for child in node.children:
                if child.type == NodeType.LIT:
                    corr_nodes = []
                    sign = 1 if child.lit > 0 else -1
                    newchildren.extend([self.nodepool[(sign*i)+self.nvars] for i in self.map[abs(child.lit)]])
                else:
                    self.__replace(child)
                    newchildren.append(child)
            node.children = newchildren
        node.count = 0

    def canonicalize(self):
        nodepool_bak = self.nodepool
        self.nodepool = [Node(NodeType.LIT, lit = i) for i in range(-self.nvars, self.nvars+1)]
        self.nodepool.extend([node for node in nodepool_bak if node.type != NodeType.LIT])
        nodepool_bak.clear()
        self.__replace(self.root)

        if len(self.fixedLits) > 0 or len(self.freeVarGroups) > 0:
            topchildren = [self.root]
            topchildren.extend([self.nodepool[i+self.nvars] for i in self.fixedLits])
            for group in self.freeVarGroups:
                if len(group) == 1:
                    node1 = self.nodepool[group[0]+self.nvars]
                    node2 = self.nodepool[-group[0]+self.nvars]
                else:
                    node1 = Node(NodeType.AND, children = [self.nodepool[i+self.nvars] for i in group])
                    node2 = Node(NodeType.AND, children = [self.nodepool[-i+self.nvars] for i in group])
                    self.nodepool.append(node1)
                    self.nodepool.append(node2)

                topchildren.append(Node(NodeType.OR, children=[node1, node2]))

            self.root = Node(NodeType.AND, children=topchildren)
            self.nodepool.append(self.root)

        self.fixedLits      = []
        self.freeVarGroups  = []
        self.map            = {}
        isCanonicalized     = True
        self.reset()

class Enumerator(object):
    '''
        Enumerator for d-DNNF
    '''

    def __init__(self, nnf, reset=False):
        self.nnf = nnf

        self.branches = []
        self.prestart = True
        self.done = False

        self.solution = list(range(1, self.nnf.nvars + 1))
        for v in self.nnf.deletedVars:
            self.solution[v-1] = None
        self.nmodels = None

        if reset:
            self.nnf.reset()

    def __search(self, node):
        if node.type == NodeType.LIT:
            self.solution[abs(node.lit) - 1] = node.lit

        elif node.type == NodeType.AND:
            for child in node.children:
                self.__search(child)

        elif node.type == NodeType.OR:
            if node.choice == None:
                node.choice = Branch.LEFT
                self.branches.append(node)
                self.__search(node.children[0])
            elif node.choice == Branch.LEFT:
                self.__search(node.children[0])
            else:
                self.__search(node.children[1])

    def next(self):
        if self.done:
            return False

        if self.prestart:
            self.__search(self.nnf.root)
            self.prestart = False
            return True
        else:
            while len(self.branches) > 0 and self.branches[-1].choice == Branch.RIGHT:
                self.branches[-1].choice = None
                self.branches.pop()

            if len(self.branches) > 0:
                self.branches[-1].choice = Branch.RIGHT
                self.__search(self.nnf.root)
                return True
            else:
                self.done = True
                return False

    def countModel(self):
        return self.nnf.root.countModels()

    def __getOf(self, node, number):
        if node.type == NodeType.LIT:
            pass
        elif node.type == NodeType.OR:
            if number < node.children[0].count:
                node.choice = Branch.LEFT
                self.branches.append(node)
                self.__getOf(node.children[0], number)
            else:
                node.choice = Branch.RIGHT
                self.branches.append(node)
                self.__getOf(node.children[1], number - node.children[0].count)
        elif node.type == NodeType.AND:
            c = node.count
            N = number
            for child in node.children:
                c = c // child.count
                q, N = divmod(N, c)
                self.__getOf(child, q)

    def get(self, number):
        if self.nnf.root.count == None:
            print('Perform model counting before you use this function.')
            return False

        if self.nnf.root.count <= number or number < 0:
            print(f'The number of models is {self.nnf.root.count}. Please specify a number less than it.')
            return False

        self.branches = []
        self.done = False
        self.prestart = False
        self.nnf.reset(False)
        self.__getOf(self.nnf.root, number)
        self.__search(self.nnf.root)
        return True