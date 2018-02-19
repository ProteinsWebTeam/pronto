#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re


class _Database:
    def __init__(self, ac):
        self.ac = ac
        self.name = None
        self.home = None
        self.color = None

    def gen_link(self):
        raise NotImplementedError()


class _Sfld(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'SFLD'
        self.home = 'http://sfld.rbvi.ucsf.edu/django'
        self.color = '#6175c3'

    def gen_link(self):
        if self.ac.startswith('SFLDF'):
            suffix = '/family/' + self.ac[5:]
        elif self.ac.startswith('SFLDS'):
            suffix = '/superfamily/' + self.ac[5:]
        else:
            suffix = '/subgroup/' + self.ac[5:]

        return self.home + suffix


class _Prodom(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'ProDom'
        self.home = 'http://prodom.prabi.fr'
        self.color = '#76b84a'

    def gen_link(self):
        return self.home + '/prodom/current/cgi-bin/request.pl?question=DBEN&query=' + self.ac


class _Prints(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'PRINTS'
        self.home = 'http://www.bioinf.manchester.ac.uk/dbbrowser/PRINTS'
        self.color = '#6a863e'

    def gen_link(self):
        return ('http://www.bioinf.manchester.ac.uk/cgi-bin/dbbrowser/sprint/searchprintss.cgi?prints_accn={}'
                '&display_opts=Prints&category=None&queryform=false&regexpr=off'.format(self.ac))


class _Pfam(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'Pfam'
        self.home = 'http://pfam.xfam.org'
        self.color = '#a36b33'

    def gen_link(self):
        return self.home + '/family/' + self.ac


class _Cdd(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'CDD'
        self.home = 'http://www.ncbi.nlm.nih.gov/Structure/cdd/cdd.shtml'
        self.color = '#a24863'

    def gen_link(self):
        return 'http://www.ncbi.nlm.nih.gov/Structure/cdd/cddsrv.cgi?uid=' + self.ac


class _PrositeProfiles(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'PROSITE profiles'
        self.home = 'http://prosite.expasy.org'
        self.color = '#60a2d9'

    def gen_link(self):
        return self.home + '/' + self.ac


class _Tigrfams(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'TIGRFAMs'
        self.home = 'http://www.jcvi.org/cgi-bin/tigrfams/index.cgi'
        self.color = '#d18dcd'

    def gen_link(self):
        return 'http://www.jcvi.org/cgi-bin/tigrfams/HmmReportPage.cgi?acc=' + self.ac


class _PrositePatterms(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'PROSITE patterns'
        self.home = 'http://prosite.expasy.org'
        self.color = '#4db395'

    def gen_link(self):
        return self.home + '/' + self.ac


class _Hamap(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'HAMAP'
        self.home = 'http://hamap.expasy.org'
        self.color = '#e1827a'

    def gen_link(self):
        return self.home + '/profile/' + self.ac


class _Smart(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'SMART'
        self.home = 'http://smart.embl-heidelberg.de'
        self.color = '#7e63d7'

    def gen_link(self):
        return self.home + '/smart/do_annotation.pl?ACC={}&BLAST=DUMMY'.format(self.ac)


class _Pirsf(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'PIRSF'
        self.home = 'http://pir.georgetown.edu/pirwww/dbinfo/pirsf.shtml'
        self.color = '#d0a242'

    def gen_link(self):
        return 'http://pir.georgetown.edu/cgi-bin/ipcSF?id=' + self.ac


class _Panther(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'PANTHER'
        self.home = 'http://www.pantherdb.org'
        self.color = '#d04d33'

    def gen_link(self):
        return self.home + '/panther/family.do?clsAccession=' + self.ac


class _CathGene3D(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'CATH-Gene3D'
        self.home = 'http://www.cathdb.info'
        self.color = '#da467b'

    def gen_link(self):
        return self.home + '/superfamily/' + re.match(r'G3DSA:(.+)', self.ac).group(1)


class _Superfamily(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'SUPERFAMILY'
        self.home = 'http://supfam.org/SUPERFAMILY'
        self.color = '#90519d'

    def gen_link(self):
        return self.home + '/cgi-bin/scop.cgi?ipid=' + self.ac


class _MobiDbLite(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'MobiDB Lite'
        self.home = 'http://mobidb.bio.unipd.it'
        self.color = '#c952bc'

    def gen_link(self):
        return self.home + '/entries/' + self.ac


class _ModBase(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'ModBase'
        self.home = 'http://modbase.compbio.ucsf.edu/modbase-cgi/index.cgi'
        self.color = '#1b9e77'

    def gen_link(self):
        return 'http://modbase.compbio.ucsf.edu/modbase-cgi-new/model_search.cgi?searchvalue={}&searchproperties=database_id&displaymode=moddetail&searchmode=default'.format(self.ac[3:])


class _PDB(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'PDB'
        self.home = 'http://www.ebi.ac.uk/pdbe'
        self.color = '#d95f02'

    def gen_link(self):
        return 'http://www.ebi.ac.uk/pdbe-srv/view/entry/{}/summary'.format(self.ac)


class _CATH(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'CATH'
        self.home = 'http://www.cathdb.info'
        self.color = '#7570b3'

    def gen_link(self):
        return self.home + '/superfamily/' + self.ac


class _SwissModel(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'SWISS-MODEL'
        self.home = 'http://swissmodel.expasy.org'
        self.color = '#e7298a'

    def gen_link(self):
        return self.home + '/repository/?pid=smr03&query_1_input=' + self.ac[3::]


class _SCOP(_Database):
    def __init__(self, ac):
        super().__init__(ac)
        self.name = 'SCOP'
        self.home = 'http://scop.mrc-lmb.cam.ac.uk/scop'
        self.color = '#66a61e'

    def gen_link(self):
        return self.home + '//search.cgi?key=/' + self.ac


def find_ref(dbcode, ac=None):
    codes = {
        # Method databases
        'B': _Sfld,
        'D': _Prodom,
        'F': _Prints,
        'H': _Pfam,
        'J': _Cdd,
        'M': _PrositeProfiles,
        'N': _Tigrfams,
        'P': _PrositePatterms,
        'Q': _Hamap,
        'R': _Smart,
        'U': _Pirsf,
        'V': _Panther,
        'X': _CathGene3D,
        'Y': _Superfamily,
        'g': _MobiDbLite,

        # Structural databases
        'A': _ModBase,
        'b': _PDB,
        'h': _CATH,
        'W': _SwissModel,
        'y': _SCOP
    }

    _DbClass = codes.get(dbcode)
    return _DbClass(ac) if _DbClass else None


def find_xref(dbcode):
    return {
        'CAZY': 'http://www.cazy.org/fam/{}.html',
        'COG': 'http://www.ncbi.nlm.nih.gov/COG/new/release/cow.cgi?cog={}',
        'EC': 'http://www.ebi.ac.uk/intenz/query?cmd=SearchEC&ec={}',
        'CATHGENE3D': 'http://www.cathdb.info/superfamily/{}',
        'GENPROP': 'http://cmr.jcvi.org/cgi-bin/CMR/shared/GenomePropDefinition.cgi?prop_acc={}',
        'INTERPRO': '/entry/{}',
        'PDBE': 'http://www.ebi.ac.uk/pdbe/entry/pdb/{}',
        'PFAM': 'http://pfam.xfam.org/family/{}',
        'PIRSF': 'http://pir.georgetown.edu/cgi-bin/ipcSF?id={}',
        'PROSITE': 'http://www.isrec.isb-sib.ch/cgi-bin/get_qdoc?{}',
        'PROSITEDOC': 'http://www.expasy.org/cgi-bin/nicedoc.pl?{}',
        'SSF': 'http://supfam.org/SUPERFAMILY/cgi-bin/scop.cgi?ipid={}',
        'SWISSPROT': 'http://www.uniprot.org/uniprot/{}',
        'TIGRFAMS': 'http://www.jcvi.org/cgi-bin/tigrfams/HmmReportPage.cgi?acc={}'
    }.get(dbcode)
