import re
from typing import List, Tuple, Dict, Optional, Any

from ase import Atoms
from ase.calculators.calculator import kptdensity2monkhorstpack
from ase.db.core import default_key_descriptions
from ase.db.table import Table, all_columns


from ase.db.core import float_to_time_string, now
from ase.geometry import cell_to_cellpar
from ase.formula import Formula


class Session:
    next_id = 1
    sessions: Dict[int, 'Session'] = {}

    def __init__(self):
        self.id = Session.next_id
        Session.next_id += 1

        Session.sessions[self.id] = self
        if len(Session.sessions) > 1000:
            # Forget old sessions:
            for id in sorted(Session.sessions)[:200]:
                del Session.sessions[id]

        self.columns = None
        self.nrows = None
        self.page = 0
        self.limit = 25
        self.sort = ''
        self.query = ''

    @staticmethod
    def get(id: int) -> 'Session':
        if id in Session.sessions:
            return Session.sessions[id]
        return Session()

    def update(self,
               page: Optional[int],
               limit: int,
               sort: str,
               toggle: str,
               default_columns: List[str]) -> None:

        if self.columns is None:
            self.columns = default_columns

        if sort:
            if sort == self.sort:
                self.sort = '-' + sort
            elif '-' + sort == self.sort:
                self.sort = 'id'
            else:
                self.sort = sort
            self.page = 0
        elif limit:
            self.limit = limit
            self.page = 0
        elif page is not None:
            self.page = page

        if toggle:
            column = toggle
            if column == 'reset':
                self.columns = default_columns[:]
            else:
                if column in self.columns:
                    self.columns.remove(column)
                    if column == self.sort.lstrip('-'):
                        self.sort = 'id'
                        self.page = 0
                else:
                    self.columns.append(column)

    @property
    def row1(self):
        return self.page * self.limit + 1

    @property
    def row2(self):
        return min((self.page + 1) * self.limit, self.nrows)

    def paginate(self) -> List[Tuple[int, str]]:
        """Helper function for pagination stuff."""
        npages = (self.nrows + self.limit - 1) // self.limit
        p1 = min(5, npages)
        p2 = max(self.page - 4, p1)
        p3 = min(self.page + 5, npages)
        p4 = max(npages - 4, p3)
        pgs = list(range(p1))
        if p1 < p2:
            pgs.append(-1)
        pgs += list(range(p2, p3))
        if p3 < p4:
            pgs.append(-1)
        pgs += list(range(p4, npages))
        pages = [(self.page - 1, 'previous')]
        for p in pgs:
            if p == -1:
                pages.append((-1, '...'))
            elif p == self.page:
                pages.append((-1, str(p + 1)))
            else:
                pages.append((p, str(p + 1)))
        nxt = min(self.page + 1, npages - 1)
        if nxt == self.page:
            nxt = -1
        pages.append((nxt, 'next'))
        return pages


def create_table(db,
                 session: Session,
                 unique_key='id'):
    query = session.query
    if session.nrows is None:
        try:
            session.nrows = db.count(query)
        except (ValueError, KeyError) as e:
            error = ', '.join(['Bad query'] + list(e.args))
            query = 'id=0'  # this will return no rows
            session.nrows = 0
        else:
            error = ''

    table = Table(db, unique_key)
    table.select(query, session.columns, session.sort,
                 session.limit, offset=session.page * session.limit)
    table.format()
    table.addcolumns = sorted(column for column in all_columns + table.keys
                              if column not in table.columns)

    return table, error


def create_key_descriptions(db) -> Dict[str, Tuple[str, str, str]]:
    kd = default_key_descriptions.copy()

    # Long description may be missing:
    for key, (short, long, unit) in kd.items():
        if not long:
            kd[key] = (short, short, unit)

    sub = re.compile(r'`(.)_(.)`')
    sup = re.compile(r'`(.*)\^\{?(.*?)\}?`')

    # Convert LaTeX to HTML:
    for key, value in kd.items():
        short, long, unit = value
        unit = sub.sub(r'\1<sub>\2</sub>', unit)
        unit = sup.sub(r'\1<sup>\2</sup>', unit)
        unit = unit.replace(r'\text{', '').replace('}', '')
        kd[key] = (short, long, unit)

    all_keys = set()
    for row in db.select(columns=['key_value_pairs'], include_data=False):
        all_keys.update(row._keys)
    for key in all_keys:
        kd[key] = (key, key, '')

    return kd


def row2things(row,
               key_descriptions: Dict[str, Tuple[str, str, str]]
               ) -> Dict[str, Any]:
    """"""

    things = {}

    atoms = Atoms(cell=row.cell, pbc=row.pbc)
    things['size'] = kptdensity2monkhorstpack(atoms,
                                              kptdensity=1.8,
                                              even=False)

    things['cell'] = [['{:.3f}'.format(a) for a in axis] for axis in row.cell]
    par = ['{:.3f}'.format(x) for x in cell_to_cellpar(row.cell)]
    things['lengths'] = par[:3]
    things['angles'] = par[3:]

    stress = row.get('stress')
    if stress is not None:
        things['stress'] = ', '.join('{0:.3f}'.format(s) for s in stress)

    things['formula'] = Formula(row.formula).format('abc')

    dipole = row.get('dipole')
    if dipole is not None:
        things['dipole'] = ', '.join('{0:.3f}'.format(d) for d in dipole)

    data = row.get('data')
    if data:
        things['data'] = ', '.join(data.keys())

    constraints = row.get('constraints')
    if constraints:
        things['constraints'] = ', '.join(c.__class__.__name__
                                          for c in constraints)

    keys = ({'id', 'energy', 'fmax', 'smax', 'mass', 'age'} |
            set(key_descriptions) |
            set(row.key_value_pairs))
    things['table'] = []
    for key in keys:
        if key == 'age':
            age = float_to_time_string(now() - row.ctime, True)
            things['table'].append(('Age', age))
            continue
        value = row.get(key)
        if value is not None:
            if isinstance(value, float):
                value = '{:.3f}'.format(value)
            elif not isinstance(value, str):
                value = str(value)
            desc, unit = key_descriptions.get(key, ['', key, ''])[1:]
            if unit:
                value += ' ' + unit
            things['table'].append((desc, value))

    return things
    