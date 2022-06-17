import base64
from tracemalloc import start
import requests
import json
import traceback

pat = None
authorization = str(base64.b64encode(bytes(':'+pat, 'ascii')), 'ascii')

STATE_CHOICES = {
    "Proposed":0,
    "Committed":1,
    "Started":2
}

RISK_ASSESSMENT_CHOICES = {
    "On Track":0,
    "At Risk":1,
    "Not On Track":2
}

def reverse_lookup(dict, value):
    return list(dict.keys())[list(dict.values()).index(value)]

class FlatQuery(object):
    def __init__(self, response):
        self.data = json.loads(response)

    def get_workItem_urls(self):
        output = []
        for wi in self.data["workItems"]:
            output.append(wi["url"])
        return output

    def get_workItems(self, fieldValues):
        urls = self.get_workItem_urls()
        output = []
        for u in urls:
            workItem = get_WorkItemExpanded(u)
            print(workItem)
            matches = True
            if fieldValues == []:
                output.append(workItem)
            else:
                for fv in fieldValues:
                    if workItem.matches_fieldValue(fv) == False:
                        matches = False
                if matches == True:
                    output.append(workItem)
        return output

class FieldValue(object):
    def __init__(self, field, values):
        self.field = field
        self.values = values

    def __repr__(self):
        return "field: "+self.field+" value:"+self.values

class Patch(object):
    def __init__(self, workItem, fieldValue):
        self.workItem = workItem
        self.fieldValue = fieldValue

    def __repr__(self):
        return "patch: "+self.workItem.get_workItemType()+": "+str(self.workItem.get_id())+" "+self.workItem.get_title()+" field: "+self.fieldValue.field+" value:"+str(self.fieldValue.values)

    def apply(self):
        return self.workItem.update_field(self.fieldValue.field, self.fieldValue.values[0])


class WorkItemExpanded(object):
    def get_by_id(id):
        url = 'https://dev.azure.com/microsoft/8d47e068-03c8-4cdc-aa9b-fc6929290322/_apis/wit/workItems/'+str(id)+'?api-version=6.0&$expand=All'
        headers = {
            'Accept': 'application/json',
            'Authorization': 'Basic '+authorization
        }
        response = requests.get(url, headers=headers)
        try:
            return WorkItemExpanded(response.text)
        except:
            print(response.text)
            return ""

    def __init__(self, response):
        self.data = json.loads(response)
        self.children = []

    def __repr__(self):
        return self.get_workItemType()+": "+self.get_title()

    def get_id(self):
        return self.data["fields"]["System.Id"]

    def get_workItemType(self):
        return self.data["fields"]["System.WorkItemType"]

    def get_riskAssessment(self):
        try:
            return self.data["fields"]["OSG.RiskAssessment"]
        except:
            return None

    def get_title(self):
        return self.data["fields"]["System.Title"]

    def get_state(self):
        return self.data["fields"]["System.State"]

    def matches_fieldValue(self, fieldValue):
        try:
            return self.data["fields"][fieldValue.field] in fieldValue.values
        except:
            return False

    def get_child_workItem_urls(self):
        output = []
        try:
            for rel in self.data["relations"]:
                if rel["attributes"]["name"] == "Child":
                    output.append(rel["url"])
        except:
            print("No relations forund")
        return output

    def load_child_workItems(self):
        urls = self.get_child_workItem_urls()
        for u in urls:
            self.children.append(get_WorkItemExpanded(u))

    def get_loaded_child_workItems(self, fieldValues):
        output = []
        if fieldValues == []:
            return self.children
        else:
            for c in self.children:
                matches = True
                for fv in fieldValues:
                    if c.matches_fieldValue(fv) == False:
                        matches = False
                if matches == True:
                    output.append(c)
            return output

    def get_child_workItems(self, fieldValues):
        urls = self.get_child_workItem_urls()
        output = []
        for u in urls:
            workItem = get_WorkItemExpanded(u)
            matches = True
            if fieldValues == []:
                output.append(workItem)
            else:
                for fv in fieldValues:
                    if workItem.matches_fieldValue(fv) == False:
                        matches = False
                if matches == True:
                    output.append(workItem)
        return output

    def update_field(self, field, value):
        url = 'https://dev.azure.com/microsoft/OS/_apis/wit/workitems/'+str(self.get_id())+'?api-version=6.0'
        body = [{'op': 'replace', 'path': '/fields/'+field, 'value': value}]
        headers = {
            'Accept': 'application/json',
            'Authorization': 'Basic '+authorization,
            'Content-type': 'application/json-patch+json'
        }
        print(self.__repr__()+" updating field: "+field+" value: "+value)
        response = requests.patch(url, json=body, headers=headers)
        print(response)
        if response.ok:
            self.add_comment("PresenceBot set "+field+" to "+value)
        return response

    def add_comment(self, text):
        url = 'https://dev.azure.com/microsoft/OS/_apis/wit/workItems/'+str(self.get_id())+'/comments?api-version=6.0-preview.3'
        body = {'text': text}
        headers = {
            'Accept': 'application/json',
            'Authorization': 'Basic '+authorization
        }
        response = requests.post(url, json=body, headers=headers)
        print(response)
        return response

    def get_patch(self, fieldValue):
        return Patch(self, fieldValue)

def get_keyresults():
    url = "https://dev.azure.com/microsoft/OS/Holoportation/_apis/wit/wiql?api-version=6.0"
    headers = {
        'Accept': 'application/json',
        'Authorization': 'Basic '+authorization
    }
    wiql = """SELECT
        [System.Id],
        [System.WorkItemType],
        [System.State],
        [System.Title],
        [Microsoft.VSTS.Common.Priority],
        [Microsoft.VSTS.Common.Triage],
        [System.AreaPath],
        [System.AssignedTo],
        [System.CreatedDate],
        [System.ChangedDate],
        [System.Tags],
        [OSG.Substatus],
        [System.Description],
        [Microsoft.VSTS.TCM.ReproSteps],
        [System.AreaLevel5],
        [System.AreaLevel6],
        [System.AreaLevel4],
        [OSG.Grade]
    FROM workitems
    WHERE
        [System.TeamProject] = @project
        AND [System.WorkItemType] = 'Key Result'
        AND [System.State] IN ('Started', 'Comitted')
        AND [System.AreaPath] UNDER 'OS\MixedReality\MeshRuntimes\Presence\Holoportation'
    ORDER BY [System.ChangedDate]"""
    body = {
        "query":wiql
    }
    response = requests.post(url, json=body, headers=headers)
    return FlatQuery(response.text)

def get_WorkItemExpanded(url):
    url = url+'?api-version=6.0&$expand=All'
    headers = {
        'Accept': 'application/json',
        'Authorization': 'Basic '+authorization
    }
    response = requests.get(url, headers=headers)
    try:
        return WorkItemExpanded(response.text)
    except Exception as e:
        traceback.print_exc()
        print(response.text)
        return ""


def bubble_up_state(dryrun=True):
    modified = []
    #get key results as a flat query
    keyResultsQuery = get_keyresults()
    #expand query results into workitems, iterate over them
    for keyResult in keyResultsQuery.get_workItems([]):
        print("keyresult: "+keyResult.get_title())
        #get scenarios for each key result
        for scenario in keyResult.get_child_workItems([FieldValue("System.WorkItemType", ["Scenario"])]):
            print("    scenario: "+scenario.get_title())
            #get deliverables for each scenario that are committed or started
            scenario.load_child_workItems()
            deliverables = scenario.get_loaded_child_workItems([])
            deliverablesCount = len(deliverables)
            #don't do caculations for scenarios with no deliverables, or if scenario is cut
            if (deliverablesCount > 0) and (scenario.get_state() != "Cut"):
                #if all are complete mark as completed
                if deliverablesCount == len(scenario.get_loaded_child_workItems([FieldValue("System.State", ["Completed"])])):
                    if(scenario.get_state() != "Completed"):
                        modified.append(scenario.get_patch(FieldValue("System.State", ["Completed"])))
                #else if any are completed or started mark as started
                elif len(scenario.get_loaded_child_workItems([FieldValue("System.State", ["Completed","Started"])])) > 0:
                    if(scenario.get_state() != "Started"):
                        modified.append(scenario.get_patch(FieldValue("System.State", ["Started"])))
                #else if any are committed mark as committed
                elif len(scenario.get_loaded_child_workItems([FieldValue("System.State", ["Committed"])])) > 0:
                    if(scenario.get_state() != "Committed"):
                        modified.append(scenario.get_patch(FieldValue("System.State", ["Committed"])))
                #else if any are proposed mark as proposed
                elif len(scenario.get_loaded_child_workItems([FieldValue("System.State", ["Proposed"])])) > 0:
                    if(scenario.get_state() != "Proposed"):
                        modified.append(scenario.get_patch(FieldValue("System.State", ["Proposed"])))

    return modified


def bubble_up_risk(dryrun=True):
    modified = []
    #get key results as a flat query
    keyResultsQuery = get_keyresults()
    #expand query results into workitems, iterate over them
    for keyResult in keyResultsQuery.get_workItems([]):
        print("keyresult: "+keyResult.get_title())
        #get scenarios for each key result
        for scenario in keyResult.get_child_workItems([FieldValue("System.WorkItemType", ["Scenario"])]):
            print("    scenario: "+scenario.get_title())
            #get deliverables for each scenario that are committed or started
            scenario.load_child_workItems()
            deliverables = scenario.get_loaded_child_workItems([])
            for d in deliverables:
                if(d.get_riskAssessment() == None):
                    modified.append(d.get_patch(FieldValue("OSG.RiskAssessment", ["On Track"])))
            deliverablesCount = len(deliverables)
            #don't do caculations for scenarios with no deliverables, or if scenario is cut
            if (deliverablesCount > 0) and (scenario.get_state() != "Cut"):
                #if all are complete mark as completed
                if deliverablesCount == len(scenario.get_loaded_child_workItems([FieldValue("OSG.RiskAssessment", ["On Track"])])):
                    if(scenario.get_riskAssessment() != "On Track"):
                        modified.append(scenario.get_patch(FieldValue("OSG.RiskAssessment", ["On Track"])))
                #else if any are completed or started mark as started
                elif len(scenario.get_loaded_child_workItems([FieldValue("OSG.RiskAssessment", ["At Risk"])])) > 0:
                    if(scenario.get_riskAssessment() != "At Risk"):
                        modified.append(scenario.get_patch(FieldValue("OSG.RiskAssessment", ["At Risk"])))
                #else if any are committed mark as committed
                elif len(scenario.get_loaded_child_workItems([FieldValue("OSG.RiskAssessment", ["Not On Track"])])) > 0:
                    if(scenario.get_riskAssessment() != "Not On Track"):
                        modified.append(scenario.get_patch(FieldValue("OSG.RiskAssessment", ["Not On Track"])))

    return modified

def push_patches(modified, dryrun=True):
    output = []
    print("Actions to take:")
    for s in modified:
        print(s)

    if dryrun == False:
        print("Taking actions now...")
        for s in modified:
            output.append(s.apply())
        print("Complete!")
    return output

statePatches = bubble_up_state(dryrun=True)
riskPatches = bubble_up_risk(dryrun=True)
stateResponses = push_patches(statePatches, dryrun=True)
riskResponses = push_patches(riskPatches, dryrun=True)