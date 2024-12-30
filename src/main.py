import os
import time
import requests
from datetime import datetime
from PIL import ImageFont, Image, ImageDraw
from trains import loadDeparturesForStation
from config import loadConfig
from open import isRun
from luma.core.interface.serial import spi, noop
from luma.core.render import canvas
from luma.oled.device import ssd1322
from luma.core.virtual import viewport, snapshot
from luma.core.sprite_system import framerate_regulator
import socket, re, uuid

def makeFont(name, size):
    font_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'fonts', name))
    return ImageFont.truetype(font_path, size, layout_engine=ImageFont.Layout.BASIC)

def renderDestination(route):
    def drawText(draw, *_):
        _, _, bitmap = cachedBitmapText(route, font)
        draw.bitmap((0, 0), bitmap, fill="orange")
    return drawText

def renderMinutes(minutes):
    def drawText(draw, width, *_):
        text = "Due" if minutes == "Due" else f"{int(minutes)} min"
        w, _, bitmap = cachedBitmapText(text, font)
        draw.bitmap((width - w, 0), bitmap, fill="orange")
    return drawText

def renderTime(draw, width, *_):
    rawTime = datetime.now().time()
    hour, minute, second = str(rawTime).split('.')[0].split(':')
    w1, _, HMBitmap = cachedBitmapText("{}:{}".format(hour, minute), fontBoldLarge)
    w2, _, _ = cachedBitmapText(':00', fontBoldTall)
    _, _, SBitmap = cachedBitmapText(':{}'.format(second), fontBoldTall)
    draw.bitmap(((width - w1 - w2) / 2, 0), HMBitmap, fill="orange")
    draw.bitmap((((width - w1 - w2) / 2) + w1, 5), SBitmap, fill="orange")

def renderDepartureStation(departureStation, xOffset):
    def draw(draw, *_):
        draw.text((int(xOffset), 0), text=departureStation, font=fontBold, fill="orange")
    return draw

bitmapRenderCache = {}

def cachedBitmapText(text, font):
    nameTuple = font.getname()
    fontKey = ''.join(nameTuple)
    key = text + fontKey
    if key in bitmapRenderCache:
        pre = bitmapRenderCache[key]
        return pre['txt_width'], pre['txt_height'], pre['bitmap']
    
    _, _, txt_width, txt_height = font.getbbox(text)
    bitmap = Image.new('L', [txt_width, txt_height], color=0)
    pre_render_draw = ImageDraw.Draw(bitmap)
    pre_render_draw.text((0, 0), text=text, font=font, fill=255)
    bitmapRenderCache[key] = {'bitmap': bitmap, 'txt_width': txt_width, 'txt_height': txt_height}
    return txt_width, txt_height, bitmap

def loadData(apiConfig, journeyConfig, config):
    try:
        departures = loadDeparturesForStation(apiConfig["apiKey"])
        if departures is None:
            return False, journeyConfig['outOfHoursName']
        return departures, None
    except requests.RequestException as err:
        print("Error: Failed to fetch data")
        print(err.__context__)
        return False, journeyConfig['outOfHoursName']

def drawBlankSignage(device, width, height, departureStation):
    device.clear()
    virtualViewport = viewport(device, width=width, height=height)
    welcomeSize = int(fontBold.getlength("Welcome to"))
    stationSize = int(fontBold.getlength(departureStation))

    rowOne = snapshot(width, 10, renderDepartureStation("Welcome to", (width - welcomeSize) / 2), interval=config["refreshTime"])
    rowTwo = snapshot(width, 10, renderDepartureStation(departureStation, (width - stationSize) / 2), interval=config["refreshTime"])
    rowTime = snapshot(width, 14, renderTime, interval=0.1)

    virtualViewport.add_hotspot(rowOne, (0, 0))
    virtualViewport.add_hotspot(rowTwo, (0, 12))
    virtualViewport.add_hotspot(rowTime, (0, 50))

    return virtualViewport

def drawSignage(device, width, height, data, station_name):
    if not data or station_name not in data or len(data[station_name]) == 0:
        return drawBlankSignage(device, width=width, height=height, departureStation=station_name)

    virtualViewport = viewport(device, width=width, height=height)
    departures = data[station_name]

    # Add station name at top
    stationSize = int(fontBold.getlength(station_name))
    rowStation = snapshot(width, 10, renderDepartureStation(
        station_name, (width - stationSize) / 2), interval=config["refreshTime"])
    virtualViewport.add_hotspot(rowStation, (0, 0))

    # Add up to 4 departures
    minutes_width = int(font.getlength("88 min"))
    for idx, departure in enumerate(departures[:3]):
        y_pos = 12 + (idx * 12)
        rowA = snapshot(width - minutes_width - 5, 10, 
                       renderDestination(departure['route']), 
                       interval=config["refreshTime"])
        rowB = snapshot(minutes_width, 10,
                       renderMinutes(departure['minutes']),
                       interval=config["refreshTime"])
        virtualViewport.add_hotspot(rowA, (0, y_pos))
        virtualViewport.add_hotspot(rowB, (width - minutes_width, y_pos))

    # Add time at bottom
    rowTime = snapshot(width, 14, renderTime, interval=0.1)
    virtualViewport.add_hotspot(rowTime, (0, 50))

    return virtualViewport

def getVersionNumber():
    version_file = open('VERSION', 'r')
    return version_file.read()

try:
    print('Starting Display v' + getVersionNumber())
    config = loadConfig()
    serial = noop() if config['headless'] else spi(port=0)
    device = ssd1322(serial, mode="1", rotate=config['screenRotation'])

    font = makeFont("Dot Matrix Regular.ttf", 10)
    fontBold = makeFont("Dot Matrix Bold.ttf", 10)
    fontBoldTall = makeFont("Dot Matrix Bold Tall.ttf", 10)
    fontBoldLarge = makeFont("Dot Matrix Bold.ttf", 20)

    widgetWidth = 256
    widgetHeight = 64

    regulator = framerate_regulator(config['targetFPS'])

    timeAtStart = time.time() - config["refreshTime"]
    timeNow = time.time()
    timeScreenSwitch = time.time() - 10
    current_station_idx = 0
    stations = []
    departures = None
    
    while True:
        with regulator:
            timeNow = time.time()
            
            if timeNow - timeScreenSwitch >= 10:
                # Refresh data on each station switch
                data = loadData(config["api"], config["journey"], config)
                if data[0] is False:
                    virtual = drawBlankSignage(
                        device, width=widgetWidth, height=widgetHeight, 
                        departureStation=data[1])
                else:
                    departures = data[0]
                    stations = list(departures.keys())
                    current_station_idx = (current_station_idx + 1) % len(stations)
                    station = stations[current_station_idx]
                    print(f"Switching to: {station} with fresh data")
                    virtual = drawSignage(device, width=widgetWidth, 
                                        height=widgetHeight, data=departures,
                                        station_name=station)
                timeScreenSwitch = timeNow

            virtual.refresh()

except KeyboardInterrupt:
    pass
except ValueError as err:
    print(f"Error: {err}")