#!/usr/bin/python
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from time import strftime, sleep
from datetime import datetime, timedelta
from pprint import pprint
from subprocess import check_output
import json, socket, hashlib, urllib2, struct, random
from threading import Thread
from collections import defaultdict
from uuid import getnode as get_mac
from urlparse import urlparse, parse_qs

mac = '%012x' % get_mac()

run_service = True

bridge_config = defaultdict(lambda:defaultdict(str))
lights_address = {}
new_lights = {}

#load config files
try:
    with open('config.json', 'r') as fp:
        bridge_config = json.load(fp)
        print("config loaded")
except Exception:
    print("config file was not loaded")

try:
    with open('lights_address.json', 'r') as fp:
        lights_address = json.load(fp)
        print("lights address loaded")
except Exception:
    print("lights adress file was not loaded")

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]

bridge_config["config"]["ipaddress"] = get_ip_address()
bridge_config["config"]["mac"] = mac[0] + mac[1] + ":" + mac[2] + mac[3] + ":" + mac[4] + mac[5] + ":" + mac[6] + mac[7] + ":" + mac[8] + mac[9] + ":" + mac[10] + mac[11]
bridge_config["config"]["bridgeid"] = mac.upper()

def save_config():
    with open('config.json', 'w') as fp:
        json.dump(bridge_config, fp, sort_keys=True, indent=4, separators=(',', ': '))
    with open('lights_address.json', 'w') as fp:
        json.dump(lights_address, fp, sort_keys=True, indent=4, separators=(',', ': '))

def ssdp_search():
    SSDP_ADDR = '239.255.255.250'
    SSDP_PORT = 1900
    MSEARCH_Interval = 2
    multicast_group_c = SSDP_ADDR
    multicast_group_s = (SSDP_ADDR, SSDP_PORT)
    server_address = ('', SSDP_PORT)
    Response_message = 'HTTP/1.1 200 OK\r\nHOST: 239.255.255.250:1900\r\nEXT:CACHE-CONTROL: max-age=100\r\nLOCATION: http://' + get_ip_address() + ':80/description.xml\r\nSERVER: Linux/3.14.0 UPnP/1.0 IpBridge/1.16.0\r\nhue-bridgeid: ' + mac.upper() + '\r\nST: urn:schemas-upnp-org:device:basic:1\r\nUSN: uuid:2f402f80-da50-11e1-9b23-' + mac
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(server_address)

    group = socket.inet_aton(multicast_group_c)
    mreq = struct.pack('4sL', group, socket.INADDR_ANY)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    print("starting ssdp...")

    while run_service:
              data, address = sock.recvfrom(1024)
              if data[0:19]== 'M-SEARCH * HTTP/1.1':
                   if data.find("ssdp:all") != -1:
                          sleep(random.randrange(0, 3))
                          print("Sending M Search response")
                          sock.sendto(Response_message, address)
              sleep(1)

def scheduler_processor():
    while run_service:
        for schedule in bridge_config["schedules"].iterkeys():
            if bridge_config["schedules"][schedule]["status"] == "enabled":
                if bridge_config["schedules"][schedule]["localtime"].startswith("W"):
                    pices = bridge_config["schedules"][schedule]["localtime"].split('/T')
                    if int(pices[0][1:]) & (1 << 6 - datetime.today().weekday()):
                        if pices[1] == datetime.now().strftime("%H:%M:%S"):
                            print("execute schedule: " + schedule)
                            sendRequest(bridge_config["schedules"][schedule]["command"]["address"], bridge_config["schedules"][schedule]["command"]["method"], json.dumps(bridge_config["schedules"][schedule]["command"]["body"]))
                elif bridge_config["schedules"][schedule]["localtime"].startswith("PT"):
                    if bridge_config["schedules"][schedule]["starttime"] == datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"):
                        print("execute timmer: " + schedule)
                        sendRequest(bridge_config["schedules"][schedule]["command"]["address"], bridge_config["schedules"][schedule]["command"]["method"], json.dumps(bridge_config["schedules"][schedule]["command"]["body"]))
                        bridge_config["schedules"][schedule]["status"] = "disabled"
                else:
                    if bridge_config["schedules"][schedule]["localtime"] == datetime.now().strftime("%Y-%m-%dT%H:%M:%S"):
                        print("execute schedule: " + schedule)
                        sendRequest(bridge_config["schedules"][schedule]["command"]["address"], bridge_config["schedules"][schedule]["command"]["method"], json.dumps(bridge_config["schedules"][schedule]["command"]["body"]))
        sleep(1)
        if (datetime.now().strftime("%M:%S") == "00:00"): #auto save configuration every hour
            save_config()

def rules_processor():
    for rule in bridge_config["rules"].iterkeys():
        if bridge_config["rules"][rule]["status"] == "enabled":
            execute = True
            seconds_delay = 0
            for condition in bridge_config["rules"][rule]["conditions"]:
                url_pices = condition["address"].split('/')
                if condition["operator"] == "eq":
                    if condition["value"] == "true":
                        if not bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]:
                            execute = False
                    elif condition["value"] == "false":
                        if bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]:
                            execute = False
                    else:
                        if not int(bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]) == int(condition["value"]):
                            execute = False
                elif condition["operator"] == "gt":
                    if not int(bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]) > int(condition["value"]):
                        execute = False
                elif condition["operator"] == "lt":
                    if int(not bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]]) < int(condition["value"]):
                        execute = False
                elif condition["operator"] == "dx":
                    if not bridge_config[url_pices[1]][url_pices[2]][url_pices[3]][url_pices[4]] == datetime.now().strftime("%Y-%m-%dT%H:%M:%S"):
                        execute = False
                elif condition["operator"] == "ddx":
                    h, m, s = condition["value"].split(':')
                    seconds_delay = int(h[2:]) * 3600 + int(m) * 60 + int(s)
            if execute:
                print("rule " + rule + " is triggered")
                for action in bridge_config["rules"][rule]["actions"]:
                    Thread(target=sendRequest, args=["/api/" + bridge_config["rules"][rule]["owner"] + action["address"], action["method"], json.dumps(action["body"]), seconds_delay]).start()

def sendRequest(url, method, data, delay=0):
    if delay != 0:
        print("delay action with " + str(delay) + " seconds")
        sleep(delay)
    if not url.startswith( 'http://' ):
        url = "http://127.0.0.1" + url
    opener = urllib2.build_opener(urllib2.HTTPHandler)
    request = urllib2.Request(url, data=data)
    request.add_header("Content-Type",'application/json')
    request.get_method = lambda: method
    opener.open(request, timeout=3)

def convert_xy(x, y, bri): #needed for milight hub that don't work with xy values
    Y = bri / 250.0
    z = 1.0 - x - y

    X = (Y / y) * x
    Z = (Y / y) * z

  # sRGB D65 conversion
    r =  X * 1.656492 - Y * 0.354851 - Z * 0.255038
    g = -X * 0.707196 + Y * 1.655397 + Z * 0.036152
    b =  X * 0.051713 - Y * 0.121364 + Z * 1.011530

    if r > b and r > g and r > 1:
    # red is too big
        g = g / r
        b = b / r
        r = 1

    elif g > b and g > r and g > 1:
    #green is too big
        r = r / g
        b = b / g
        g = 1

    elif b > r and b > g and b > 1:
    # blue is too big
        r = r / b
        g = g / b
        b = 1

  # Apply gamma correction  if device_data["hue"] == "strip" else
    r = 12.92 * r if r <= 0.0031308 else (1.0 + 0.055) * pow(r, (1.0 / 2.4)) - 0.055
    g = 12.92 * g if g <= 0.0031308 else (1.0 + 0.055) * pow(g, (1.0 / 2.4)) - 0.055
    b = 12.92 * b if b <= 0.0031308 else (1.0 + 0.055) * pow(b, (1.0 / 2.4)) - 0.055
    #r = r <= 0.0031308 ? 12.92 * r : (1.0 + 0.055) * pow(r, (1.0 / 2.4)) - 0.055
    #g = g <= 0.0031308 ? 12.92 * g : (1.0 + 0.055) * pow(g, (1.0 / 2.4)) - 0.055
    #b = b <= 0.0031308 ? 12.92 * b : (1.0 + 0.055) * pow(b, (1.0 / 2.4)) - 0.055

    if r > b and r > g:
    # red is biggest
        if r > 1:
            g = g / r
            b = b / r
            r = 1
        elif g > b and g > r:
        # green is biggest
            if g > 1:
                r = r / g
                b = b / g
                g = 1

        elif b > r and b > g:
        # blue is biggest
            if b > 1:
                r = r / b
                g = g / b
                b = 1

    r = 0 if r < 0 else r
    g = 0 if g < 0 else g
    b = 0 if b < 0 else b

    return [int(r * 255), int(g * 255), int(b * 255)]

def sendLightRequest(light, data):
    payload = {}
    if lights_address[light]["protocol"] == "native": #ESP8266 light or strip
        url = "http://" + lights_address[light]["ip"] + "/set?light=" + str(lights_address[light]["light_nr"]);
        method = 'GET'
        for key, value in data.iteritems():
            if key == "xy":
                url += "&x=" + str(value[0]) + "&y=" + str(value[1])
            else:
                url += "&" + key + "=" + str(value)
    elif lights_address[light]["protocol"] == "milight": #MiLight bulb
        url = "http://" + lights_address[light]["ip"] + "/gateways/" + lights_address[light]["device_id"] + "/" + lights_address[light]["mode"] + "/" + str(lights_address[light]["group"]);
        method = 'PUT'
        for key, value in data.iteritems():
            if key == "on":
                payload["status"] = value
            elif key == "bri":
                payload["brightness"] = value
            elif key == "ct":
                payload["color_temp"] = int((500 - value) / 1.6 + 153)
            elif key == "hue":
                payload["hue"] = value / 180
            elif key == "sat":
                payload["saturation"] = value * 100 / 255
            elif key == "xy":
                (payload["r"], payload["g"], payload["b"]) = convert_xy(value[0], value[1], bridge_config["lights"][light]["state"]["bri"])
        print(json.dumps(payload))
    elif lights_address[light]["protocol"] == "ikea_tradfri": #IKEA Tradfri bulb
        url = "coaps://" + lights_address[light]["ip"] + ":5684/15001/" + str(lights_address[light]["device_id"])
        for key, value in data.iteritems():
            if key == "on":
                payload["5850"] = int(value)
            elif key == "transitiontime":
                payload["5712"] = value
            elif key == "bri":
                payload["5851"] = value
            elif key == "ct":
                if value < 270:
                    payload["5706"] = "f5faf6"
                elif value < 385:
                    payload["5706"] = "f1e0b5"
                else:
                    payload["5706"] = "efd275"
            elif key == "xy":
                payload["5709"] = int(value[0] * 65535)
                payload["5710"] = int(value[1] * 65535)
        if "5712" not in payload:
            payload["5712"] = 4
        if "5850" in payload and payload["5850"] == 0:
            payload.clear() #setting brightnes will turn on the ligh even if there was a request to power off
            payload["5850"] = 0
        pprint(payload)

    try:
        if lights_address[light]["protocol"] == "ikea_tradfri":
            print(check_output("./coap-client-linux -m put -u \"Client_identity\" -k \"" + lights_address[light]["security_code"] + "\" -e '{ \"3311\": [" + json.dumps(payload) + "] }' \"" + url + "\"", shell=True).split("\n")[3])
        else:
            sendRequest(url, method, json.dumps(payload))
    except:
        bridge_config["lights"][light]["state"]["reachable"] = False
        print("request error")
    else:
        bridge_config["lights"][light]["state"]["reachable"] = True
    print("LightRequest: " + url)

def update_group_stats(light): #set group stats based on lights status in that group
    for group in bridge_config["groups"]:
        if light in bridge_config["groups"][group]["lights"]:
            for key, value in bridge_config["lights"][light]["state"].iteritems():
                if key not in ["on", "reachable"]:
                    bridge_config["groups"][group]["action"][key] = value
            any_on = False
            all_on = True
            bri = 0
            for group_light in bridge_config["groups"][group]["lights"]:
                if bridge_config["lights"][light]["state"]["on"] == True:
                    any_on = True
                else:
                    all_on = False
                bri += bridge_config["lights"][light]["state"]["bri"]
            avg_bri = bri / len(bridge_config["groups"][group]["lights"])
            bridge_config["groups"][group]["state"] = {"any_on": any_on, "all_on": all_on, "bri": avg_bri, "lastupdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")}


def scan_for_lights(): #scan for ESP8266 lights and strips
    print(json.dumps([{"success": {"/lights": "Searching for new devices"}}], sort_keys=True, indent=4, separators=(',', ': ')))
    #return all host that listen on port 80
    device_ips = check_output("nmap  " + get_ip_address() + "/24 -p80 --open -n | grep report | cut -d ' ' -f5", shell=True).split("\n")
    del device_ips[-1] #delete last empty element in list
    for ip in device_ips:
        if ip != get_ip_address():
            try:
                f = urllib2.urlopen("http://" + ip + "/detect")
                device_data = json.loads(f.read())
                if device_data.keys()[0] == "hue":
                    print(ip + " is a hue " + device_data['hue'])
                    device_exist = False
                    for light in bridge_config["lights"].iterkeys():
                        if bridge_config["lights"][light]["uniqueid"].startswith( device_data["mac"] ):
                            device_exist = True
                            lights_address[light]["ip"] = ip
                    if not device_exist:
                        print("is a new device")
                        for x in xrange(1, int(device_data["lights"]) + 1):
                            i = 1
                            while (str(i)) in bridge_config["lights"]:
                                i += 1
                            bridge_config["lights"][str(i)] = {"state": {"on": False, "bri": 200, "hue": 0, "sat": 0, "xy": [0.0, 0.0], "ct": 461, "alert": "none", "effect": "none", "colormode": "ct", "reachable": True}, "type": "Extended color light", "name": "Hue " + device_data["type"] + " " + device_data["hue"] + " " + str(x), "uniqueid": device_data["mac"] + "-" + str(x), "modelid": "LST001" if device_data["hue"] == "strip" else "LCT001", "swversion": "66009461"}
                            new_lights.update({str(i): {"name": "Hue " + device_data["type"] + " " + device_data["hue"] + " " + str(x)}})
                            lights_address[str(i)] = {"ip": ip, "light_nr": x, "protocol": "native"}
            except Exception, e:
                print(ip + " is unknow device " + str(e))

def syncWithTradfri(): #update Hue Bridge lights states from Ikea Tradfri gateway
    for light in lights_address:
        if lights_address[light]["protocol"] == "ikea_tradfri":
            light_stats = json.loads(check_output("./coap-client-linux -m get -u \"Client_identity\" -k \"" + lights_address[light]["security_code"] + "\" \"coaps://" + lights_address[light]["ip"] + ":5684/15001/" + str(lights_address[light]["device_id"]) +"\"", shell=True).split("\n")[3])
            bridge_config["lights"][light]["state"]["on"] = bool(light_stats["3311"][0]["5850"])
            bridge_config["lights"][light]["state"]["bri"] = light_stats["3311"][0]["5851"]
            if light_stats["3311"][0]["5706"] == "f5faf6":
                bridge_config["lights"][light]["state"]["ct"] = 170
            elif light_stats["3311"][0]["5706"] == "f1e0b5":
                bridge_config["lights"][light]["state"]["ct"] = 320
            elif light_stats["3311"][0]["5706"] == "efd275":
                bridge_config["lights"][light]["state"]["ct"] = 470


def description():
    return """<root xmlns=\"urn:schemas-upnp-org:device-1-0\">
<specVersion>
<major>1</major>
<minor>0</minor>
</specVersion>
<URLBase>http://""" + get_ip_address() + """:80/</URLBase>
<device>
<deviceType>urn:schemas-upnp-org:device:Basic:1</deviceType>
<friendlyName>Philips hue</friendlyName>
<manufacturer>Royal Philips Electronics</manufacturer>
<manufacturerURL>http://www.philips.com</manufacturerURL>
<modelDescription>Philips hue Personal Wireless Lighting</modelDescription>
<modelName>Philips hue bridge 2015</modelName>
<modelNumber>BSB002</modelNumber>
<modelURL>http://www.meethue.com</modelURL>
<serialNumber>""" + mac.upper() + """</serialNumber>
<UDN>MYUUID</UDN>
<presentationURL>index.html</presentationURL>
<iconList>
<icon>
<mimetype>image/png</mimetype>
<height>48</height>
<width>48</width>
<depth>24</depth>
<url>hue_logo_0.png</url>
</icon>
<icon>
<mimetype>image/png</mimetype>
<height>120</height>
<width>120</width>
<depth>24</depth>
<url>hue_logo_3.png</url>
</icon>
</iconList>
</device>
</root>"""

def webform_tradfri():
    return """<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>Tradfri Setup</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/purecss@0.6.2/build/pure-min.css\">
</head>
<body>
<form class=\"pure-form pure-form-aligned\" action=\"\" method=\"get\">
<fieldset>
<legend>Tradfri Setup</legend>
<div class=\"pure-control-group\"><label for=\"ip\">Bridge IP</label><input id=\"ip\" name=\"ip\" type=\"text\" placeholder=\"168.168.xxx.xxx\"></div>
<div class=\"pure-control-group\"><label for=\"code\">Security Code</label><input id=\"code\" name=\"code\" type=\"text\" placeholder=\"1a2b3c4d5e6f7g8h\"></div>
<div class=\"pure-controls\"><label for=\"cb\" class=\"pure-checkbox\"></label><button type=\"submit\" class=\"pure-button pure-button-primary\">Save</button></div>
</fieldset>
</form>
</body>
</html>"""


def webform_milight():
    return """<!doctype html>
<html>
<head>
<meta charset=\"utf-8\">
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
<title>Milight Setup</title>
<link rel=\"stylesheet\" href=\"https://unpkg.com/purecss@0.6.2/build/pure-min.css\">
</head>
<body>
<form class=\"pure-form pure-form-aligned\" action=\"\" method=\"get\">
<fieldset>
<legend>Milight Setup</legend>
<div class=\"pure-control-group\"><label for=\"ip\">Hub ip</label><input id=\"ip\" name=\"ip\" type=\"text\" placeholder=\"168.168.xxx.xxx\"></div>
<div class=\"pure-control-group\"><label for=\"device_id\">Device id</label><input id=\"device_id\" name=\"device_id\" type=\"text\" placeholder=\"0x1234\"></div>
<div class=\"pure-control-group\">
<label for=\"mode\">Mode</label>
<select id=\"mode\" name=\"mode\">
<option value=\"rgbw\">RGBW</option>
<option value=\"cct\">CCT</option>
<option value=\"rgb_cct\">RGB+CCT</option>
<option value=\"rgb\">RGB</option>
</select>
</div>
<div class=\"pure-control-group\">
<label for=\"group\">Group</label>
<select id=\"group\" name=\"group\">
<option value=\"1\">1</option>
<option value=\"2\">2</option>
<option value=\"3\">3</option>
<option value=\"4\">4</option>
</select>
</div>
<div class=\"pure-controls\"><button type=\"submit\" class=\"pure-button pure-button-primary\">Save</button></div>
</fieldset>
</form>
</body>
</html>"""


def update_all_lights():
    ## apply last state on startup to all bulbs, usefull if there was a power outage
    for light in bridge_config["lights"]:
        payload = {}
        payload["on"] = bridge_config["lights"][light]["state"]["on"]
        payload["bri"] = bridge_config["lights"][light]["state"]["bri"]
        payload[bridge_config["lights"][light]["state"]["colormode"]] = bridge_config["lights"][light]["state"][bridge_config["lights"][light]["state"]["colormode"]]
        Thread(target=sendLightRequest, args=[light, payload]).start()
        sleep(0.5)
        print("update status for light " + light)

class S(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

    def do_GET(self):
        self._set_headers()
        if self.path == '/description.xml':
            self.wfile.write(description())
        elif self.path.startswith("/tradfri"): #setup Tradfri gateway
            get_parameters = parse_qs(urlparse(self.path).query)
            if "code" in get_parameters:
                tradri_devices = json.loads(check_output("./coap-client-linux -m get -u \"Client_identity\" -k \"" + get_parameters["code"][0] + "\" \"coaps://" + get_parameters["ip"][0] + ":5684/15001\"", shell=True).split("\n")[3])
                pprint(tradri_devices)
                lights_found = 0
                for device in tradri_devices:
                    device_parameters = json.loads(check_output("./coap-client-linux -m get -u \"Client_identity\" -k \"" + get_parameters["code"][0] + "\" \"coaps://" + get_parameters["ip"][0] + ":5684/15001/" + str(device) +"\"", shell=True).split("\n")[3])
                    if "3311" in device_parameters:
                        lights_found += 1
                        #register new tradfri light
                        print("register tradfi light " + device_parameters["9001"])
                        i = 1
                        while (str(i)) in bridge_config["lights"]:
                            i += 1
                        bridge_config["lights"][str(i)] = {"state": {"on": False, "bri": 200, "hue": 0, "sat": 0, "xy": [0.0, 0.0], "ct": 461, "alert": "none", "effect": "none", "colormode": "ct", "reachable": True}, "type": "Extended color light", "name": device_parameters["9001"], "uniqueid": "1234567" + str(device), "modelid": "LLM010", "swversion": "66009461"}
                        new_lights.update({str(i): {"name": device_parameters["9001"]}})
                        lights_address[str(i)] = {"device_id": device, "security_code": get_parameters["code"][0], "ip": get_parameters["ip"][0], "protocol": "ikea_tradfri"}
                if lights_found == 0:
                    self.wfile.write(webform_tradfri() + "<br> No lights where found")
                else:
                    self.wfile.write(webform_tradfri() + "<br> " + str(lights_found) + " lights where found")
            else:
                self.wfile.write(webform_tradfri())
        elif self.path.startswith("/milight"): #setup milight bulb
            get_parameters = parse_qs(urlparse(self.path).query)
            if "device_id" in get_parameters:
                #register new mi-light
                i = 1
                while (str(i)) in bridge_config["lights"]:
                    i += 1
                bridge_config["lights"][str(i)] = {"state": {"on": False, "bri": 200, "hue": 0, "sat": 0, "xy": [0.0, 0.0], "ct": 461, "alert": "none", "effect": "none", "colormode": "ct", "reachable": True}, "type": "Extended color light", "name": "MiLight " + get_parameters["mode"][0] + " " + get_parameters["device_id"][0], "uniqueid": "1a2b3c4" + str(random.randrange(0, 99)), "modelid": "LCT001", "swversion": "66009461"}
                new_lights.update({str(i): {"name": "MiLight " + get_parameters["mode"][0] + " " + get_parameters["device_id"][0]}})
                lights_address[str(i)] = {"device_id": get_parameters["device_id"][0], "mode": get_parameters["mode"][0], "group": int(get_parameters["group"][0]), "ip": get_parameters["ip"][0], "protocol": "milight"}
                self.wfile.write(webform_milight() + "<br> Light added")
            else:
                self.wfile.write(webform_milight())
        elif self.path.startswith("/switch"): #request from an ESP8266 switch or sensor
            get_parameters = parse_qs(urlparse(self.path).query)
            pprint(get_parameters)
            if "devicetype" in get_parameters: #register device request
                sensor_is_new = True
                for sensor in bridge_config["sensors"]:
                    if get_parameters["mac"][0] == bridge_config["sensors"][sensor]["uniqueid"]:# if sensor is already present
                        sensor_is_new = False
                if sensor_is_new:
                    print("registering new sensor " + get_parameters["devicetype"][0])
                    i = 1 #find first empty sensor id
                    while (str(i)) in bridge_config["sensors"]:
                        i += 1
                    bridge_config["sensors"][str(i)] = {"state": {"buttonevent": 0, "lastupdated": "none"}, "config": {"on": True, "battery": 100, "reachable": True}, "name": "Dimmer Switch" if get_parameters["devicetype"][0] == "ZLLSwitch" else "Tap Switch", "type": get_parameters["devicetype"][0], "modelid": "RWL021" if get_parameters["devicetype"][0] == "ZLLSwitch" else "ZGPSWITCH", "manufacturername": "Philips", "swversion": "5.45.1.17846" if get_parameters["devicetype"][0] == "ZLLSwitch" else "", "uniqueid": get_parameters["mac"][0]}
            else: #switch action request
                for sensor in bridge_config["sensors"]:
                    if get_parameters["mac"][0] == bridge_config["sensors"][sensor]["uniqueid"]: #match senser id based on mac address
                        bridge_config["sensors"][sensor]["state"].update({"buttonevent": get_parameters["button"][0], "lastupdated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})
                        rules_processor() #process the rules to perform the action configured by application
        else:
            url_pices = self.path.split('/')
            if url_pices[2] in bridge_config["config"]["whitelist"]: #if username is in whitelist
                bridge_config["config"]["UTC"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
                bridge_config["config"]["localtime"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                if len(url_pices) == 3: #print entire config
                    self.wfile.write(json.dumps(bridge_config))
                elif len(url_pices) == 4: #print specified object config
                    if url_pices[3] == "lights": #add changes from IKEA Tradfri gateway to bridge
                        syncWithTradfri()
                    self.wfile.write(json.dumps(bridge_config[url_pices[3]]))
                elif len(url_pices) == 5:
                    if url_pices[4] == "new": #return new lights and sensors only
                        new_lights.update({"lastscan": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})
                        self.wfile.write(json.dumps(new_lights))
                        new_lights.clear()
                    else:
                        self.wfile.write(json.dumps(bridge_config[url_pices[3]][url_pices[4]]))
                elif len(url_pices) == 6:
                    self.wfile.write(json.dumps(bridge_config[url_pices[3]][url_pices[4]][url_pices[5]]))
            elif (url_pices[2] == "nouser" or url_pices[2] == "config"): #used by applications to discover the bridge
                self.wfile.write(json.dumps({"name": bridge_config["config"]["name"],"datastoreversion": 59, "swversion": bridge_config["config"]["swversion"], "apiversion": bridge_config["config"]["apiversion"], "mac": bridge_config["config"]["mac"], "bridgeid": bridge_config["config"]["bridgeid"], "factorynew": False, "modelid": bridge_config["config"]["modelid"]}))
            else: #user is not in whitelist
                self.wfile.write(json.dumps([{"error": {"type": 1, "address": self.path, "description": "unauthorized user" }}]))


    def do_POST(self):
        self._set_headers()
        print "in post method"
        self.data_string = self.rfile.read(int(self.headers['Content-Length']))
        post_dictionary = json.loads(self.data_string)
        url_pices = self.path.split('/')
        print(self.path)
        print(self.data_string)
        if len(url_pices) == 4: #data was posted to a location
            if url_pices[2] in bridge_config["config"]["whitelist"]:
                if ((url_pices[3] == "lights" or url_pices[3] == "sensors") and not bool(post_dictionary)):
                    #if was a request to scan for lights of sensors
                    Thread(target=scan_for_lights).start()
                    sleep(7) #give no more than 7 seconds for light scanning (otherwise will face app disconnection timeout)
                    self.wfile.write(json.dumps([{"success": {"/" + url_pices[3]: "Searching for new devices"}}]))
                else: #create object
                    # find the first unused id for new object
                    i = 1
                    while (str(i)) in bridge_config[url_pices[3]]:
                        i += 1
                    if url_pices[3] == "scenes":
                        post_dictionary.update({"lightstates": {}, "version": 2, "picture": "", "lastupdated": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")})
                    elif url_pices[3] == "groups":
                        post_dictionary.update({"action": {"on": False}, "state": {"any_on": False, "all_on": False}})
                    elif url_pices[3] == "schedules":
                        post_dictionary.update({"created": datetime.now().strftime("%Y-%m-%dT%H:%M:%S")})
                        if post_dictionary["localtime"].startswith("PT"):
                            timmer = post_dictionary["localtime"][2:]
                            (h, m, s) = timmer.split(':')
                            d = timedelta(hours=int(h), minutes=int(m), seconds=int(s))
                            post_dictionary.update({"starttime": (datetime.utcnow() + d).strftime("%Y-%m-%dT%H:%M:%S")})
                        if not "status" in post_dictionary:
                            post_dictionary.update({"status": "enabled"})
                    elif url_pices[3] == "rules":
                        post_dictionary.update({"owner": url_pices[2]})
                        if not "status" in post_dictionary:
                            post_dictionary.update({"status": "enabled"})
                    bridge_config[url_pices[3]][str(i)] = post_dictionary
                    print(json.dumps([{"success": {"id": str(i)}}], sort_keys=True, indent=4, separators=(',', ': ')))
                    self.wfile.write(json.dumps([{"success": {"id": str(i)}}], sort_keys=True, indent=4, separators=(',', ': ')))
            else:
                self.wfile.write(json.dumps([{"error": {"type": 1, "address": self.path, "description": "unauthorized user" }}],sort_keys=True, indent=4, separators=(',', ': ')))
                print(json.dumps([{"error": {"type": 1, "address": self.path, "description": "unauthorized user" }}],sort_keys=True, indent=4, separators=(',', ': ')))
        elif "devicetype" in post_dictionary: #this must be a new device registration
                #create new user hash
                s = hashlib.new('ripemd160', post_dictionary["devicetype"][0]        ).digest()
                username = s.encode('hex')
                bridge_config["config"]["whitelist"][username] = {"last use date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),"create date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),"name": post_dictionary["devicetype"]}
                self.wfile.write(json.dumps([{"success": {"username": username}}], sort_keys=True, indent=4, separators=(',', ': ')))
                print(json.dumps([{"success": {"username": username}}], sort_keys=True, indent=4, separators=(',', ': ')))
        self.end_headers()
        save_config()

    def do_PUT(self):
        self._set_headers()
        print "in PUT method"
        self.data_string = self.rfile.read(int(self.headers['Content-Length']))
        put_dictionary = json.loads(self.data_string)
        url_pices = self.path.split('/')
        if url_pices[2] in bridge_config["config"]["whitelist"]:
            if len(url_pices) == 4:
                bridge_config[url_pices[3]].update(put_dictionary)
                response_location = "/" + url_pices[3] + "/"
            if len(url_pices) == 5:
                if url_pices[3] == "schedules":
                    if "status" in put_dictionary and put_dictionary["status"] == "enabled" and bridge_config["schedules"][url_pices[4]]["localtime"].startswith("PT"):
                        if "localtime" in put_dictionary:
                            timmer = put_dictionary["localtime"][2:]
                        else:
                            timmer = bridge_config["schedules"][url_pices[4]]["localtime"][2:]
                        (h, m, s) = timmer.split(':')
                        d = timedelta(hours=int(h), minutes=int(m), seconds=int(s))
                        put_dictionary.update({"starttime": (datetime.utcnow() + d).strftime("%Y-%m-%dT%H:%M:%S")})
                bridge_config[url_pices[3]][url_pices[4]].update(put_dictionary)
                response_location = "/" + url_pices[3] + "/" + url_pices[4] + "/"
            if len(url_pices) == 6:
                if url_pices[3] == "groups": #state is applied to a group
                    if "scene" in put_dictionary: #if group is 0 and there is a scene applied
                        for light in bridge_config["scenes"][put_dictionary["scene"]]["lights"]:
                            bridge_config["lights"][light]["state"].update(bridge_config["scenes"][put_dictionary["scene"]]["lightstates"][light])
                            Thread(target=sendLightRequest, args=[light, bridge_config["scenes"][put_dictionary["scene"]]["lightstates"][light]]).start()
                            update_group_stats(light)
                    elif "bri_inc" in put_dictionary:
                        bridge_config["groups"][url_pices[4]]["action"]["bri"] += int(put_dictionary["bri_inc"])
                        if bridge_config["groups"][url_pices[4]]["action"]["bri"] > 254:
                            bridge_config["groups"][url_pices[4]]["action"]["bri"] = 254
                        elif bridge_config["groups"][url_pices[4]]["action"]["bri"] < 1:
                            bridge_config["groups"][url_pices[4]]["action"]["bri"] = 1
                        bridge_config["groups"][url_pices[4]]["state"]["bri"] = bridge_config["groups"][url_pices[4]]["action"]["bri"]
                        del put_dictionary["bri_inc"]
                        put_dictionary.update({"bri": bridge_config["groups"][url_pices[4]]["action"]["bri"]})
                        for light in bridge_config["groups"][url_pices[4]]["lights"]:
                            bridge_config["lights"][light]["state"].update(put_dictionary)
                            Thread(target=sendLightRequest, args=[light, put_dictionary]).start()
                    elif url_pices[4] == "0":
                        for light in bridge_config["lights"].iterkeys():
                            bridge_config["lights"][light]["state"].update(put_dictionary)
                            Thread(target=sendLightRequest, args=[light, put_dictionary]).start()
                            for group in bridge_config["groups"].iterkeys():
                                bridge_config["groups"][group][url_pices[5]].update(put_dictionary)
                                if put_dictionary["on"]:
                                    bridge_config["groups"][group]["state"]["any_on"] = put_dictionary["on"]
                                    bridge_config["groups"][group]["state"]["all_on"] = put_dictionary["on"]
                    else: # the state is applied to particular group (url_pices[4])
                        for light in bridge_config["groups"][url_pices[4]]["lights"]:
                                bridge_config["lights"][light]["state"].update(put_dictionary)
                                Thread(target=sendLightRequest, args=[light, put_dictionary]).start()
                elif url_pices[3] == "lights": #state is applied to a light
                    Thread(target=sendLightRequest, args=[url_pices[4], put_dictionary]).start()
                    for key in put_dictionary.iterkeys():
                        if key in ["ct", "xy", "hue"]: #colormode must be set by bridge
                            bridge_config["lights"][url_pices[4]]["state"]["colormode"] = key
                    update_group_stats(url_pices[4])
                if not url_pices[4] == "0": #group 0 is virtual, must not be saved in bridge configuration
                    try:
                        bridge_config[url_pices[3]][url_pices[4]][url_pices[5]].update(put_dictionary)
                    except KeyError:
                        bridge_config[url_pices[3]][url_pices[4]][url_pices[5]] = put_dictionary
                if url_pices[3] == "sensors" and "flag" in put_dictionary: #if a scheduler change te flag of a logical sensor then process the rules.
                    rules_processor()
                response_location = "/" + url_pices[3] + "/" + url_pices[4] + "/" + url_pices[5] + "/"
            if len(url_pices) == 7:
                try:
                    bridge_config[url_pices[3]][url_pices[4]][url_pices[5]][url_pices[6]].update(put_dictionary)
                except KeyError:
                    bridge_config[url_pices[3]][url_pices[4]][url_pices[5]][url_pices[6]] = put_dictionary
                bridge_config[url_pices[3]][url_pices[4]][url_pices[5]][url_pices[6]] = put_dictionary
                response_location = "/" + url_pices[3] + "/" + url_pices[4] + "/" + url_pices[5] + "/" + url_pices[6] + "/"
            response_dictionary = []
            for key, value in put_dictionary.iteritems():
                response_dictionary.append({"success":{response_location + key: value}})
            self.wfile.write(json.dumps(response_dictionary,sort_keys=True, indent=4, separators=(',', ': ')))
            print(json.dumps(response_dictionary, sort_keys=True, indent=4, separators=(',', ': ')))
        else:
            self.wfile.write(json.dumps([{"error": {"type": 1, "address": self.path, "description": "unauthorized user" }}],sort_keys=True, indent=4, separators=(',', ': ')))

    def do_DELETE(self):
        self._set_headers()
        url_pices = self.path.split('/')
        if url_pices[2] in bridge_config["config"]["whitelist"]:
            del bridge_config[url_pices[3]][url_pices[4]]
            if url_pices[3] == "lights":
                del lights_address[url_pices[4]]
            self.wfile.write(json.dumps([{"success": "/" + url_pices[3] + "/" + url_pices[4] + " deleted."}]))

def run(server_class=HTTPServer, handler_class=S):
    server_address = ('', 80)
    httpd = server_class(server_address, handler_class)
    print 'Starting httpd...'
    httpd.serve_forever()

if __name__ == "__main__":
    try:
        Thread(target=ssdp_search).start()
        Thread(target=scheduler_processor).start()
        update_all_lights()
        run()
    except:
        print("server stopped")
    finally:
        run_service = False
        save_config()
        print 'config saved'
