## diyHue
This project emulates a Philips Hue Bridge that is able to control IKEA Tradfri lights (usign Tradfri Bridge), Mi-Light lights (using MiLight Hub), Neopixel strips (WS2812B and SK6812) and any cheep ESP8266 based bulb from market by replacing firmware with custom one. Is written in python and will run on all small boxes like RaspberryPi. There are provided sketches for Dimmer Switch and Tap Switch  

[![IMAGE ALT TEXT HERE](https://img.youtube.com/vi/c6MsG3oIehY/0.jpg)](https://www.youtube.com/watch?v=c6MsG3oIehY)


### Requirements:
 - python
 - nmap package for lights autodiscover

## TO DO
 - ~~control IKEA Trådfri lights from HUE applications~~
 - ~~Create ESP8266 bridge device to add MI Lights to Hue Bridge emulator.~~
 - Cleanup the code
 
## Working futures:
  - Control lights (all functions)
  - Control groups (all functions)
  - Scenes (all functions)
  - Routines
  - Wake up
  - Go to sleep
  - Switches (custom esp8266 switches)
  - Autodiscover lights

## Not working:
  - Home & Away futures
  - Schedules with random time (no application use this)
  

## IKEA TRADFRI
Open http://{bridgeIP}/tradfri, type Ikea bridge ip and security key and click "Save". If everything was fine you will see all lights paired with Tradfri bridge in Hue application.
Important: coap-client-linux binary is compiled for arm devices like raspberry pi. If you will use an x86 computer then you will need to recompile this.

## MI-LIGHT:
esp8266_milight_hub is required https://github.com/sidoh/esp8266_milight_hub.
Open http://{bridgeIP}/milight, complete the form and click Save. You need to repet this step for every light as there is no way to retrive the list of lights from milight hub. 

## NEOPIXEL STRIPS:
Wi-fi connection is setup using WiFiManager https://github.com/tzapu/WiFiManager
There is support for both WS2812B (rgb) and SK6812 (rgbw) smart leds (neopixels). Data in pin of the strip must be connected to rx pin of esp8266 device. In order to compile the sketch you must download NeoPixelBus (by Makuna) and WiFiManager (by tzapu) libraries available in Arduino library manager. Is possible to emulate more lights in one strip by setting lightsCount value to any value. I recommend about 3 lights per strip in order to have nice scenes.

## GENERIC PWM LIGHTS:

Most of wifi bulbs and strip controllers from the market are esp8266 based and control the brightness of leds using pwm. The only real difference from them is the number/order of the output pins. If you intend to buy some cheap wifi bulbs/strips and want to use this project you will need to check how hard is to flash the firmware in that light. So far i use only "Color Dreams" wifi bulbs and i was not able to flash the firmware easy using external serial adapter connected directly to ESP8266 pins. However for me was not that hard to replace the SPI flash chip from these bulbs with ones already flashed on WEMOS d1 mini pro, but i have some electronics skills and was not first time when i replace an SOT8 chip.

#### Options in skeches:
 - ```lightsCount x ``` //number of emulated lights per strip, available only for neopixels stript
 - ```pixelCount xx``` // number of leds in strip, available only for neopixels strips
 - ```IPAddress strip_ip ( xxx,  xxx,   xxx,  xxx);``` //if you want to use static ip uncommented with gateway_ip, subnet_mask and WiFi.config(strip_ip, gateway_ip, subnet_mask) line.
lights can be controlled from internal GUI or with hue api via http GET of POST. example url:  
```
"http://{light ip}/set?light=1&r=0&g=60&b=255&transitiontime=2000"
"http://{light ip}/discover"
```
list of arguments that can be passed in url:
  - "on": 1 to set light on, 0 to set the light off.
  - "r", "g", "b": setup light color using rbg values between 0 and 255.
  - "x" and "y": values between 0.0 and 1.0 to setup light color in CIE chart.
  - "ct": value between 153 (max warm white) and 500 (max could white) http://en.wikipedia.org/wiki/Mired
  - hue: value between 0 and 65535, represent the hue of the light.
  - sat: saturation of the light. 255 is the most saturated and 0 is the least saturated.
  - bri: brightness of the light, 255 is the maximum brightness, 1 is the minimum, 0 will turn the light on to previews state
  - transitiontime: duration of the transition from the light’s current state to the new stat. default 4 represent 0.4 seconds.
  - bri_inc: uncrease or decrease the brightness with a specified value

Contributions are welcomed  

Credits: 
  - probonopd https://github.com/probonopd/ESP8266HueEmulator
  - sidoh https://github.com/sidoh/esp8266_milight_hub

