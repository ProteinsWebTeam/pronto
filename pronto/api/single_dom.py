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
    
    keep = set()
    discard = set()

    for domain1 in sorted(domains, reverse=True):
        for domain2 in sorted(domains, reverse=True):
            if domain1 != domain2 or (domain1 == domain2 and len(domains[domain1]) > 1):
                for dom1 in domains[domain1]:
                    start1, end1, sign1, colour1, short1 = dom1
                    dom1len = end1 - start1 + 1
                    sign2 = sign1
                    if dom1 not in discard:
                        for dom2 in domains[domain2]:
                            max_overlap = 0
                            start2, end2, sign2, colour2, short2 = dom2
                            dom2len = end2 - start2 + 1

                            if dom2 not in discard and dom1 != dom2:
                                overlap = min(end1, end2) - max(start1, start2) + 1
                                max_overlap = max(max_overlap, overlap)

                                if max_overlap > 0:
                                    if max_overlap > 0.7*dom1len and max_overlap > 0.7*dom2len:
                                        if dom1len > dom2len:
                                            keep.add(dom1)
                                            discard.add(dom2)
                                        elif dom1len < dom2len:
                                            keep.add(dom2)
                                            discard.add(dom1)

                                        elif dom1len == dom2len:
                                            if re.match(r'^PF', sign1): #give priority to Pfam domain
                                                keep.add(dom1)
                                                if dom2 in keep:
                                                    keep.remove(dom2)
                                                discard.add(dom2)
                                            elif re.match(r'^PF', sign2):
                                                keep.add(dom2)
                                                if dom1 in keep:
                                                    keep.remove(dom1)
                                                discard.add(dom2)
                                            else:
                                                keep.add(dom1)
                                                if dom2 in keep:
                                                    keep.remove(dom2)
                                                discard.add(dom2)
                                    elif max_overlap < 0.7*dom1len and max_overlap > 0.7*dom2len:
                                        keep.add(dom1)
                                        discard.add(dom2)
                                    elif max_overlap > 0.7*dom1len and max_overlap < 0.7*dom2len:
                                        keep.add(dom1)
                                        discard.add(dom1)
                                    else:
                                        keep.add(dom1)
                                elif max_overlap <= 0:
                                    keep.add(dom1)
                        if dom1 not in discard:
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
