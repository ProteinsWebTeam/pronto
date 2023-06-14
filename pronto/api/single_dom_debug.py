import sys, re, json, ssl
from urllib import request
from urllib.error import HTTPError
from time import sleep

from flask import Blueprint, jsonify

bp = Blueprint("api_single_dom", __name__, url_prefix="/api/single_dom")

@bp.route("/<protein_acc>/")
def get_single_domain(protein_acc):

    domains = get_domains_from_api(protein_acc)
    sequence = get_protein_seq(protein_acc)

    return jsonify({
        "accession": protein_acc,
        "sequence": sequence,
        "sequence_len": len(sequence),
        "domains": domains
    })

def find_overlap(domains):
    # protein_list= ['Q7X923', 'Q2QZF2', 'P02144', 'P42212', 'P00519', 'P0CJ46', 'O00206', 'P15559', 'P27245', 'B8V7R6', 'Q99895', 'Q9UUQ6', 'P00634', 'D5KQK4', 'A0A013VK40', 'P21865']
    
    keep = set()
    discard = set()

    for domain1 in sorted(domains, reverse=True):
        # print("discard: ", discard)
        for domain2 in sorted(domains, reverse=True):
            # print(domains[domain1], domains[domain2])
            if domain1 != domain2 or (domain1 == domain2 and len(domains[domain1]) > 1):
                # keep, discard = is_overlapping(domains[dom1], domains[dom2], keep, discard)
                for dom1 in domains[domain1]:
                    start1, end1, sign1, colour1, short1 = dom1
                    dom1len = end1 - start1 + 1
                    sign2 = sign1
                    if dom1 not in discard:
                        to_keep = dom1
                        for dom2 in domains[domain2]:
                            max_overlap = 0
                            # print("begin:", dom1, dom2, to_keep)
                            # print("keep_dom: ", keep_dom)
                            start2, end2, sign2, colour2, short2 = dom2
                            dom2len = end2 - start2 + 1

                            if dom2 not in discard and dom1 != dom2:
                                # print("compare: ", dom1, dom2)
                                overlap = min(end1, end2) - max(start1, start2) + 1
                                max_overlap = max(max_overlap, overlap)

                                # print("max_overlap:", max_overlap)
                                if max_overlap > 0:
                                    if max_overlap > 0.7*dom1len and max_overlap > 0.7*dom2len:
                                        if dom1len > dom2len:
                                            to_keep = dom1
                                            keep.add(dom1)
                                            discard.add(dom2)
                                            # print("keep:", dom1, "discard: ", dom2)
                                            # print("discarded: ", sign2)
                                        elif dom1len < dom2len:
                                            keep.add(dom2)
                                            to_keep = dom2
                                            discard.add(dom1)
                                            # print("keep:", dom2, "discard: ", dom1)
                                        elif dom1len == dom2len:
                                            if re.match(r'^PF', sign1): #give priority to Pfam domain
                                                keep.add(dom1)
                                                to_keep = dom1
                                                if dom2 in keep:
                                                    keep.remove(dom2)
                                                discard.add(dom2)
                                                # print("keep:", dom1, "discard: ", dom2)
                                            elif re.match(r'^PF', sign2):
                                                keep.add(dom2)
                                                if dom1 in keep:
                                                    keep.remove(dom1)
                                                to_keep = dom2
                                                discard.add(dom2)
                                                # print("keep:", dom2, "discard: ", dom1)
                                            else:
                                                keep.add(dom1)
                                                to_keep = dom1
                                                if dom2 in keep:
                                                    keep.remove(dom2)
                                                discard.add(dom2)
                                                # print("keep:", dom1, "discard: ", dom2)
                                    elif max_overlap < 0.7*dom1len and max_overlap > 0.7*dom2len:
                                        keep.add(dom1)
                                        to_keep = dom1
                                        discard.add(dom2)
                                        # print("one side overlap dom2, overlap:", max_overlap," keep:", dom1, "discard: ", dom2)
                                    elif max_overlap > 0.7*dom1len and max_overlap < 0.7*dom2len:
                                        keep.add(dom1)
                                        to_keep = dom2
                                        discard.add(dom1)
                                        # print("one side overlap dom1 keep:", dom2, "discard: ", dom1)
                                    else:
                                        # print("keep:", dom1)
                                        keep.add(dom1)
                                        
                                elif max_overlap <= 0:
                                    keep.add(dom1)
                                    to_keep = dom1
                                    # print("no overlap keep:", dom1)
                        if dom1 not in discard:
                            # print("not in discard: ", dom1)
                            keep.add(dom1)    
        try:
            discard.add(dom1)    
        except:
            pass

    return keep
            

def sort_by_length(domains: dict):
    keep = find_overlap(domains)
                
    if len(keep) == 0:
        for dom in sorted(domains, reverse=True):
            for domain in domains[dom]:
                keep.add(domain)

    json_output = []
    for item in sorted(list(keep), key=lambda x:x[0]):
        json_output.append({"accession":item[2], "start":item[0], "end":item[1], "color":item[3], "short_name":item[4]})

    return json_output

def get_protein_seq(protein_ac: str):
    next = f"https://www.ebi.ac.uk/interpro/wwwapi/protein/UniProt/{protein_ac}/"
    last_page = False
    context = ssl._create_unverified_context()
    
    attempts = 0
    while next:
        try:
            req = request.Request(next, headers={"Accept": "application/json"})
            res = request.urlopen(req, context=context)
            if res.status == 408:
                sleep(61)
                continue
            elif res.status == 204:
                break
            payload = json.loads(res.read().decode())
            next = ""
            attempts = 0
            if not next:
                last_page = True
        except HTTPError as e:
            if e.code == 408:
                sleep(61)
                continue
            else:
                if attempts < 3:
                    attempts += 1
                    sleep(61)
                    continue
                else:
                    sys.stderr.write("LAST URL: " + next)
                    raise e

        sequence = payload["metadata"]["sequence"]
        
        if next:
            sleep(1)
    
    return sequence

def get_domains_from_api(protein_ac: str):
   
    base_url = f"https://www.ebi.ac.uk:443/interpro/wwwapi/entry/all/protein/UniProt/{protein_ac}/?extra_fields=short_name&page_size=200"
    all_domains = output_list(base_url)

    single_domains = sort_by_length(all_domains)

    return single_domains


def output_list(base_url: str):
    #disable SSL verification to avoid config issues

    member_db = ["pfam", "smart", "pirsf", "ncbifam", "hamap", "sfld", "cdd", "profile"]
    colours = {"cdd": '#addc58', "hamap": '#2cd6d6', "pfam": '#6287b1', "pirsf": '#fbbddd', 
               "profile": '#f69f74', "sfld": '#00b1d3', "smart": '#ff8d8d', "ncbifam": '#56b9a6'}
    context = ssl._create_unverified_context()

    next = base_url
    last_page = False
    
    attempts = 0
    while next:
        try:
            req = request.Request(next, headers={"Accept": "application/json"})
            res = request.urlopen(req, context=context)
            if res.status == 408:
                sleep(61)
                continue
            elif res.status == 204:
                break
            payload = json.loads(res.read().decode())
            next = payload["next"]
            attempts = 0
            if not next:
                last_page = True
        except HTTPError as e:
            if e.code == 408:
                sleep(61)
                continue
            else:
                if attempts < 3:
                    attempts += 1
                    sleep(61)
                    continue
                else:
                    sys.stderr.write("LAST URL: " + next)
                    raise e

        domains = dict()
        for i, item in enumerate(payload["results"]):
            
            accession = item["metadata"]["accession"]
            type = item["metadata"]["type"]
            member = item["metadata"]["source_database"]
            short_name = item["extra_fields"]["short_name"]

            if type != "site" and member in member_db:
                for dom in item["proteins"][0]["entry_protein_locations"]:
                    for frag in dom["fragments"]:
                        start = frag["start"]
                        end = frag["end"]
                        dom_len = end - start +1
                        
                        if dom_len:
                            try:
                                domains[dom_len].append((start, end, accession, colours[member], short_name))
                            except KeyError:
                                domains[dom_len] = [(start, end, accession, colours[member], short_name)]
                        else:
                            print(f"nothing found {accession}")

        if next:
            sleep(1)
    
    return domains

def get_domains(cur, protein_ac: str):
    #should we take into account InterPro type instead of member db type when integrated?
    request = """
            select m.method_ac, m.pos_from, m.pos_to
            from interpro.match m
            join interpro.method me on m.method_ac=me.method_ac
            where m.protein_ac=:1
            and m.dbcode in ('H', 'R', 'N', 'U', 'Q', 'B', 'J', 'M')
            and me.sig_type != 'S'
        """
    cur.execute(request, (protein_ac,))

    domains = {}
    for row in cur:
        try:
            start = row[1]
            end = row[2]
            dom_len = int(end) - int(start) + 1
            domains[dom_len].append((start, end, row[0]))
        except KeyError:
            domains[dom_len] = [(start, end, row[0])]

    # print(domains)
    sort_by_length(domains)



#new results
# Q7X923
# {162: [(19, 181, 'PF14826')], 83: [(824, 907, 'PF08512')], 151: [(543, 694, 'PF08644'), (543, 694, 'SM01286')], 229: [(197, 426, 'PF00557')], 243: [(195, 438, 'cd01091')], 164: [(19, 183, 'SM01285')], 90: [(819, 909, 'SM01287')]}
# [(19, 183, 'SM01285'), (195, 438, 'cd01091'), (543, 694, 'PF08644'), (819, 909, 'SM01287')]

# Q2QZF2
# {82: [(11, 93, 'PF18052')], 199: [(285, 484, 'PF00931')], 22: [(700, 722, 'SM00369')], 23: [(746, 769, 'SM00369'), (793, 816, 'SM00369')]}
# [(11, 93, 'PF18052'), (285, 484, 'PF00931'), (700, 722, 'SM00369'), (746, 769, 'SM00369'), (793, 816, 'SM00369')]

# P02144
# {112: [(28, 140, 'PF00042')], 148: [(6, 154, 'cd08926')], 145: [(3, 148, 'PS01033')]}
# [(6, 154, 'cd08926')]

# P42212
# {193: [(17, 210, 'PF01353')]}
# [(17, 210, 'PF01353')]

# P00519
# {103: [(1027, 1130, 'PF08919')], 75: [(127, 202, 'PF00017')], 46: [(67, 113, 'PF00018')], 250: [(242, 492, 'PF07714')], 93: [(123, 216, 'cd09935')], 53: [(65, 118, 'cd11850')], 262: [(235, 497, 'cd05052')], 126: [(1004, 1130, 'SM00808')], 83: [(125, 208, 'SM00252')], 251: [(242, 493, 'SM00219'), (242, 493, 'PS50011')], 56: [(64, 120, 'SM00326')], 90: [(127, 217, 'PS50001')], 60: [(61, 121, 'PS50002')]}
# [(61, 121, 'PS50002'), (123, 216, 'cd09935'), (235, 497, 'cd05052'), (1004, 1130, 'SM00808')]

# P0CJ46
# {372: [(5, 377, 'PF00022')], 173: [(10, 183, 'cd00012')], 370: [(7, 377, 'SM00268')]}
# [(5, 377, 'PF00022')]

# O00206
# {127: [(5, 132, 'PIRSF037595')], 66: [(332, 398, 'PIRSF037595')], 145: [(392, 537, 'PIRSF037595'), (673, 818, 'SM00255')], 304: [(518, 822, 'PIRSF037595')], 255: [(78, 333, 'PIRSF037595')], 60: [(127, 187, 'PF13855')], 57: [(57, 114, 'PF13855')], 61: [(447, 508, 'PF13855')], 163: [(676, 839, 'PF01582')], 24: [(201, 225, 'SM00369'), (470, 494, 'SM00369'), (149, 173, 'SM00369'), (149, 173, 'SM00365')], 23: [(101, 124, 'SM00369'), (77, 100, 'SM00369'), (421, 444, 'SM00369'), (495, 518, 'SM00369'), (176, 199, 'PS51450')], 19: [(57, 76, 'SM00369'), (1, 20, 'PS51257')], 21: [(174, 195, 'SM00369'), (519, 540, 'SM00369'), (372, 393, 'SM00369'), (421, 442, 'SM00365'), (174, 195, 'SM00365'), (495, 516, 'SM00365')], 49: [(579, 628, 'SM00082')], 22: [(398, 420, 'SM00365')], 143: [(672, 815, 'PS50104')]}
# [(5, 132, 'PIRSF037595'), (78, 333, 'PIRSF037595'), (332, 398, 'PIRSF037595'), (392, 537, 'PIRSF037595'), (518, 822, 'PIRSF037595')]

# P15559
# {206: [(5, 211, 'PF02525')]}
# [(5, 211, 'PF02525')]

# P27245
# {58: [(38, 96, 'PF01047')], 101: [(31, 132, 'SM00347')], 133: [(11, 144, 'PS50995')]}
# [(11, 144, 'PS50995')]

# B8V7R6
# {58: [(513, 571, 'PF01391')], 57: [(567, 624, 'PF01391'), (288, 345, 'PF01391'), (3, 60, 'PF01391')], 222: [(661, 883, 'PF01410')], 227: [(657, 884, 'SM00038')], 223: [(661, 884, 'PS51461')]}
# [(3, 60, 'PF01391'), (288, 345, 'PF01391'), (513, 571, 'PF01391'), (567, 624, 'PF01391'), (657, 884, 'SM00038')]

# Q99895
# {232: [(30, 262, 'PF00089')], 235: [(30, 265, 'cd00190')], 233: [(29, 262, 'SM00020')], 237: [(30, 267, 'PS50240')]}
# [(30, 267, 'PS50240')]

# Q9UUQ6
# {300: [(288, 588, 'SFLDG01018'), (288, 588, 'SFLDG01212')], 279: [(296, 575, 'PF00494')], 287: [(292, 579, 'cd00683')], 89: [(144, 233, 'TIGR03462'), (3, 92, 'TIGR03462')]}
# [(3, 92, 'TIGR03462'), (144, 233, 'TIGR03462'), (288, 588, 'SFLDG01018')]

# P00634
# {367: [(64, 431, 'PF00245')], 404: [(65, 469, 'cd16012')], 406: [(65, 471, 'SM00098')]}
# [(65, 471, 'SM00098')]

# D5KQK4
# {86: [(49, 135, 'PF00234')], 103: [(38, 141, 'cd00261')], 90: [(49, 139, 'SM00499')]}
# [(38, 141, 'cd00261')]

# A0A013VK40
# {109: [(58, 167, 'PF07715')], 579: [(396, 975, 'PF00593')]}
# [(58, 167, 'PF07715'), (396, 975, 'PF00593')]

# P21865
# {104: [(403, 507, 'PF13493')], 117: [(527, 644, 'PF13492')], 105: [(777, 882, 'PF02518')], 65: [(665, 730, 'PF00512'), (661, 726, 'cd00082')], 209: [(21, 230, 'PF02702')], 101: [(778, 879, 'cd00075')], 120: [(253, 373, 'cd01987')], 67: [(663, 730, 'SM00388')], 110: [(773, 883, 'SM00387')], 213: [(670, 883, 'PS50109')]}
# [(21, 230, 'PF02702'), (253, 373, 'cd01987'), (403, 507, 'PF13493'), (527, 644, 'PF13492'), (670, 883, 'PS50109')]
