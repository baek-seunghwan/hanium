#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import xml.etree.ElementTree as ET
import sys

ns = {
    'dct': 'http://purl.org/dc/terms/',
    'foaf': 'http://xmlns.com/foaf/0.1/',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'dcat': 'http://www.w3.org/ns/dcat#',
    'vcard': 'http://www.w3.org/2006/vcard/ns#'
}

FN = 'data.xml'
try:
    root = ET.parse(FN).getroot()
except Exception as e:
    print('Error parsing', FN + ':', e)
    sys.exit(1)


def find_text(path):
    el = root.find(path, ns)
    return el.text.strip() if el is not None and el.text else ''


def find_attr(path, attr_name):
    el = root.find(path, ns)
    if el is None:
        return ''
    # try namespaced rdf:resource first
    rdf_key = '{%s}%s' % (ns['rdf'], attr_name)
    return el.attrib.get(rdf_key) or el.attrib.get(attr_name) or ''


print('Title:', find_text('.//dct:title'))
print('Description:', find_text('.//dct:description'))
print('Issued:', find_text('.//dct:issued'))
print('Modified:', find_text('.//dct:modified'))
print('Publisher:', find_text('.//dct:publisher/foaf:name'))
print('Contact unit:', find_text('.//vcard:organization-unit'))

telephone = find_attr('.//vcard:hasTelephone', 'resource')
if telephone:
    print('Telephone (rdf:resource):', telephone)

endpoint = find_attr('.//dcat:endpointURL', 'resource')
if endpoint:
    print('Endpoint URL:', endpoint)

landing = find_attr('.//dcat:landingPage', 'resource')
if landing:
    print('Landing Page:', landing)

print('Format:', find_text('.//dcat:format'))
print('Theme:', find_text('.//dcat:theme'))
print('Keywords:')
for el in root.findall('.//dcat:keyword', ns):
    if el.text:
        print(' -', el.text.strip())

print('Spatial:', find_text('.//dct:spatial'))
print('Temporal:', find_text('.//dct:temporal'))
