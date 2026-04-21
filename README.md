# espStreamer
Arduino-based project for CHrome/ESP32-S3 to make it handle a live stream and convert it to C64 compatible image 

Prereq:
- Windows (because of powershell)
- Chrome or other compatible browser.
- VLC installed on the machine (and in path)
- Python installed on machine (and in path)
- Powershell (a newer version to be safe)
- An ESP32 if you want to use that optional part. It need to the programmed with the ArduinoIde project included. I used a ESP32-S3 Dev Board (16MB/8MB) but othere might work too.
- VICE or other emulator if you want to be able to click on the created PRG/CRT files and see them running directly.

Currently, the application can be used in 2 ways:
- Running Partly on ESP32, poentially closer to C64. End goal is to have it fully running on ESP32 for mobility, like a cartridge or plug-in device.
- Running fully in Chrome on a PC/Mac/Linux device. This is optimal for performace. A Proxy written in Python is used.

You switch hosting model using the buttons on top: "ESP32 / Locally".

Instructions:
- Run the Start command and that will pretty much start everything.

The powershell script tries to select the left-most screen of your desktop and start a VLC stream for that screen, regardless of resolution. In my case I have a 2560x1440 monitor there.
It then scales that down to 160x200 (C64 multicolor resolution), caps it to a resonable biterate and waits for incoming clients.

The web app should start and you should see a downscaled version of you desktop directly in the browser if everythins worked.
As a trouble-shoot step you can start another VLC instance as a client and connect to network Stream at: @:90/mjpeg.X. You should see the live stream running.
NOTE: You should be running all clients (web or VLC) in a second screen to not get the classic picture-inpciture problem.

TIP:A cool demo, that I use a lot, is to visit 3d-page that shows different 3d models that you can rotate.

SETTINGS:
To change the parameters for the actual stream you need to open the "start.bat" file in a text editor and change them manually and then restart the script.
Resolution (320x200 or 160x200 being the best alternatives) , Frames Per Second (5 to 30 maybe good) and bitrate (400 to 2000 is good values) are the most usuable parameters that can make a difference.

In the web app you can change:
- ESP32 IP Address
- Image formats
- Output formats: PRG/KOA/CRT
- Dither algorithm and strength
- Scale (is used as an optimizing part in the JPG algorithm if your having a really bad connection.)
- Brightness/Contrast
- Ratio: Different ways of handling the rescaling to either crop or fit the original screen
- Choose background color, can optimize some images to look much better

The web app has 2 dinstinct ways of creating output C64 files:
- A single image mode which just sets the correct color mode and show the image. Both PRG and CRT can be created.
- A slideshow C64 app that takes all your CAPTURED images and shows them continously and in a loop.
- UPCOMING: There will also be a animation mode which saves images as fast as possible until the CRT are full (about 100 unpacked full koala images) and then creates a C64 animation app that just shows the animation. Like the slideshow but without pause between images.

The bottom part 

Information shown is:
- STATUS - Are we connected to a stream
- FPS: Total Frames per Second this instant
- Total: Number of bytes transferred in total through the link.
