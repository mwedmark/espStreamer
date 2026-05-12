# espStreamer
Arduino-based project for Chrome/ESP32-S3 to make it handle a live stream and convert it to C64 compatible image.
It can create either PRG/CRT files which holds both the viewer and the actual image data or a KOA-file which is just the image data.
It can also create small slideshows of maximum 3 images in a PRG/CRT file.
NOTE: CRT export still has bugs after the 2 first images. Needs more work.

This solution uses a webapp for control/view from a webbrowser(tested on Chrome) and also uses Python script where applicable.
It is also possible to run this without a ESP32. In this case only a Python environment and webbrowser is needed.

Prereq:
- Windows (because of powershell)
- Chrome or other compatible browser.
- VLC installed on the machine (and in path)
- Python installed on machine (and in path)
- Powershell (a newer version to be safe)
- An ESP32 if you want to use that optional part. It need to the programmed with the ArduinoIde project included. I used a ESP32-S3 Dev Board (16MB/8MB) but others might work too.
  You might need to change build settings for the project in ArduinoIde.
- VICE or other emulator if you want to be able to click on the created PRG/CRT files and see them running directly or stream live into VICE.

Currently, the application can be used in 2 ways:
- Running Partly on ESP32, pontially closer to C64. End goal is to have it fully running on ESP32 for mobility, like a cartridge or plug-in device.
- Running fully in Chrome on a PC/Mac/Linux device. This is optimal for performace. A Proxy written in Python is used.

Best performance is given by the non-ESP32 solution, because then your powerful PC does all the work.
The ESP32 solution gives a more mobile solution that can be closer to C64, maybe like a cartridge/device.
From now it also supports talking directly to C64 or VICE emulator and showing streams or single images there.

You switch hosting model using the buttons on top: "ESP32 / Locally".

Instructions:
- Run the Start command to start the main streaming part of the app.
The powershell script tries to select the left-most screen of your desktop and start a VLC stream for that screen, regardless of resolution. In my case I have a 2560x1440 monitor there.
It then scales that down to 160x200 (C64 multicolor resolution), caps it to a resonable biterate and waits for incoming clients.

The web app should then start and you should see a downscaled version of you desktop directly in the browser if everythins worked.
As a trouble-shoot step you can start another VLC instance as a client and connect to network Stream at: @:90/mjpeg.X 
You should see the live stream running.
NOTE: You should be running all clients (web or VLC) in a second screen to not get the classic picture-in-picture problem.

TIP: A cool demo, that I use a lot, is to visit 3d-page that shows different 3d models that you can rotate.

SETTINGS:
To change the parameters for the actual stream you need to open the "start.bat" file in a text editor and change them manually and then restart the script.
Resolution (320x200 or 160x200 being the best alternatives) , Frames Per Second (5 to 30 maybe good) and bitrate (400 to 2000 is good values) are the most usuable parameters that can make a difference.

In the web app you can change:
- ESP32 IP Address (I should add some local DNS name here so it can find it itself)
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
- IDEA: There will also be a animation mode which saves images as fast as possible until the CRT are full (about 100 unpacked full koala images) and then creates a C64 animation app that just shows the animation. Like the slideshow but without pause between images.

TEH BOTTOM PART

Information shown is:
- STATUS - Are we connected to a stream
- FPS: Total Frames per Second this instant
- Total: Number of bytes transferred in total through the link.

HARDWARE CONTROL PART
- You can choose between connecting to a already started instance of VICE or conneting to a running C64 via Kung Fu Flash 1/2 USB-connection.

Description on how to get haradware working:

VICE flow:
To get VICE working you need to make sure to enable the binary machine monitor at port 6511 which is currently hard-coded in EspStreamer
So start VICE and enable monitor, then choose VICE as alternative and click "CONNECT". It should now be connected to VICE.
Via this port it can pause and inject memory changes into C64 and then release it to update graphics. When running streaming, we do this at a default rate if 10 fps (every 100ms) which seem to work ok.
We also support sending changes to graphics modes, which makes the C64 mirror the current format you've chosen in the web app. You can also just send an image as a screen shot.

C64+Kung Fu Flash flow:
You need to make sure to connect you're Kung Fu Flash to the C64 and start the machine and stay in the Kung Fu Flash menu for the USB-connection to be open.
Choose Kung Fu Flash in the menu and click "CONNECT", it should now say connected. Then you choose to send "Viewer PRG over USB". This will make C64 update screen and actually receive and execute the viewer app.
After that it will listen to the same stuff that the VICE-app does:
- "Start Stream" will make the C64 go into correct graphics mode and just wait for incoming images.
- "Send Image" choose the correct graphics mode and receives a single image.

You switch between image/Stream mode at any time and you can also change type of image and C64/VICE should follow by changing modes.
