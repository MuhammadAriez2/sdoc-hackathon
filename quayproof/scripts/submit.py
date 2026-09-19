#!/usr/bin/env python3
"""Submit your output to an organizer-authorized endpoint; show aggregate score only."""
import argparse,json,urllib.request

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True,help='Organizer-authorized server URL')
    p.add_argument('--file',default='submission.json')
    args=p.parse_args()
    with open(args.file,encoding='utf-8') as file:submission=json.load(file)
    req=urllib.request.Request(args.url.rstrip('/')+'/submit',data=json.dumps(submission).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=120) as response:result=json.load(response)
    score=result.get('final_score')
    if isinstance(score,(int,float)):print(json.dumps({'final_score':score},indent=2))
    else:print('Submission sent. No numeric final_score returned; no per-case data displayed.')

if __name__=='__main__':main()
