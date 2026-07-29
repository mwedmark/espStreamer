# espStreamer
Started as an Arduino-based project for Chrome/ESP32-S3 to make it handle a live stream and convert it to C64 compatible image.
Going forward the ESP32 is actually not needed but still supported. See below 
It can create either PRG/CRT files which holds both the viewer and the actual image data or a KOA-file which is just the image data.
It can also create small slideshows of maximum 3 images in a PRG/CRT file.
NOTE: CRT export still has bugs after the 2 first images. Needs more work.

This solution uses a webapp for control/view from a webbrowser(tested on Chrome) and also uses Python script where applicable.
It is also possible to run this without a ESP32. In this case only a Python environment and webbrowser is needed.

## PREREQ:
- Windows (because of powershell)
- Chrome or other compatible browser.
- VLC installed on the machine (and in path)
- Python installed on machine (and in path)
- Powershell (a newer version to be safe)
- An ESP32 if you want to use that optional part. It need to the programmed with the ArduinoIde project included. I used a ESP32-S3 Dev Board (16MB/8MB) but others might work too.
  You might need to change build settings for the project in ArduinoIde.
- VICE or other emulator if you want to be able to click on the created PRG/CRT files and see them running directly or stream live into VICE.

## WAYS TO START
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

## SETTINGS
To change the parameters for the actual stream you need to open the "start.bat" file in a text editor and change them manually and then restart the script.
Resolution (320x200 or 160x200 being the best alternatives) , Frames Per Second (5 to 30 maybe good) and bitrate (400 to 2000 is good values) are the most usuable parameters that can make a differ[...[...]

In the web app you can change:
- ESP32 IP Address (I should add some local DNS name here so it can find it itself)
- Image formats
- Output formats: PRG/KOA/CRT
- Dither algorithm and strength
- Scale (is used as an optimizing part in the JPG algorithm if your having a really bad connection.)
- Brightness/Contrast
- Ratio: Different ways of handling the rescaling to either crop or fit the original screen
- Choose background color, can optimize some images to look much better

## OUTPUT - WHAT DOES IT ACTUALLY DO?
The web app has 2 dinstinct ways of creating output C64 files:
- A single image mode which just sets the correct color mode and show the image. Both PRG and CRT can be created.
- A slideshow C64 app that takes all your CAPTURED images and shows them continously and in a loop.
- IDEA: There will also be a animation mode which saves images as fast as possible until the CRT are full (about 100 unpacked full koala images) and then creates a C64 animation app that just show[...[...]

## THE BOTTOM PART - HARDWARE CONTROL PART

Information shown is:
- STATUS - Are we connected to a stream
- FPS: Total Frames per Second this instant
- Total: Number of bytes transferred in total through the link.

You can choose between connecting to a already started instance of VICE or conneting to a running C64 via Kung Fu Flash 1/2 USB-connection.

## HOW TO START STREAMING
Description on how to get hardware working:

VICE flow:
To get VICE working you need to make sure to enable the binary machine monitor at port 6511 which is currently hard-coded in EspStreamer
So start VICE and enable monitor, then choose VICE as alternative and click "CONNECT". It should now be connected to VICE.
Via this port it can pause and inject memory changes into C64 and then release it to update graphics. When running streaming, we do this at a default rate if 10 fps (every 100ms) which seem to wor[...[...]
We also support sending changes to graphics modes, which makes the C64 mirror the current format you've chosen in the web app. You can also just send an image as a screen shot.

C64+Kung Fu Flash flow:
You need to make sure to connect you're Kung Fu Flash to the C64 and start the machine and stay in the Kung Fu Flash menu for the USB-connection to be open.
Choose Kung Fu Flash in the menu and click "CONNECT", it should now say connected. Then you choose to send "Viewer PRG over USB". This will make C64 update screen and actually receive and execute [...[...]
After that it will listen to the same stuff that the VICE-app does:
- "Start Stream" will make the C64 go into correct graphics mode and just wait for incoming images.
- "Send Image" choose the correct graphics mode and receives a single image.

You switch between image/Stream mode at any time and you can also change type of image and C64/VICE should follow by changing modes.

And a gallery of images and videos from the implementation phase:

## Gallery

<div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; padding: 20px 0;">

<!-- Videos -->
<div style="text-align: center;">
  <a href="docs/images/C64VidDig.mp4" target="_blank">
    <video width="280" height="auto" style="border: 1px solid #ccc; border-radius: 4px;" poster="">
      <source src="docs/images/C64VidDig.mp4" type="video/mp4">
      Your browser does not support the video tag.
    </video>
  </a>
  <p><strong>C64VidDig.mp4</strong><br><small>Video Demo</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/LastDemo_KFFLive_20260517_185933.mp4" target="_blank">
    <video width="280" height="auto" style="border: 1px solid #ccc; border-radius: 4px;" poster="">
      <source src="docs/images/LastDemo_KFFLive_20260517_185933.mp4" type="video/mp4">
      Your browser does not support the video tag.
    </video>
  </a>
  <p><strong>LastDemo_KFFLive</strong><br><small>Latest Live Demo (May 2026)</small></p>
</div>

<!-- Images -->
<div style="text-align: center;">
  <a href="docs/images/CartoonCar.webp" target="_blank">
    <img src="docs/images/CartoonCar.webp" alt="CartoonCar" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>CartoonCar</strong><br><small>Cartoon Car Demo</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/CombinedWebApp&VICE.webp" target="_blank">
    <img src="docs/images/CombinedWebApp&VICE.webp" alt="CombinedWebApp&VICE" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Combined WebApp & VICE</strong><br><small>WebApp with VICE Emulator</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/EarlySettingsHR.webp" target="_blank">
    <img src="docs/images/EarlySettingsHR.webp" alt="EarlySettingsHR" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Early Settings HR</strong><br><small>High Resolution Settings</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/EarlySettingsMC.webp" target="_blank">
    <img src="docs/images/EarlySettingsMC.webp" alt="EarlySettingsMC" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Early Settings MC</strong><br><small>Multicolor Settings</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/Earlyimage.webp" target="_blank">
    <img src="docs/images/Earlyimage.webp" alt="Earlyimage" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Early Image 1</strong><br><small>Early Development</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/Earlyimage2.webp" target="_blank">
    <img src="docs/images/Earlyimage2.webp" alt="Earlyimage2" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Early Image 2</strong><br><small>Early Development Phase 2</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/FiatEarlyIFLI.webp" target="_blank">
    <img src="docs/images/FiatEarlyIFLI.webp" alt="FiatEarlyIFLI" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Fiat Early IFLI</strong><br><small>IFLI Mode - Fiat</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/FirstColorImage.webp" target="_blank">
    <img src="docs/images/FirstColorImage.webp" alt="FirstColorImage" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>First Color Image</strong><br><small>First Successful Color Output</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/FirstWorkingPRG.webp" target="_blank">
    <img src="docs/images/FirstWorkingPRG.webp" alt="FirstWorkingPRG" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>First Working PRG</strong><br><small>First Functional PRG File</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/ForzaFullScreen.webp" target="_blank">
    <img src="docs/images/ForzaFullScreen.webp" alt="ForzaFullScreen" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Forza Full Screen</strong><br><small>Forza Racing Game Stream</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/KoalaViewerDemo.webp" target="_blank">
    <img src="docs/images/KoalaViewerDemo.webp" alt="KoalaViewerDemo" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Koala Viewer Demo</strong><br><small>Koala Format Viewer</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/MonsterEarlyIFLI.webp" target="_blank">
    <img src="docs/images/MonsterEarlyIFLI.webp" alt="MonsterEarlyIFLI" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Monster Early IFLI</strong><br><small>IFLI Mode - Monster</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/PassatBW.webp" target="_blank">
    <img src="docs/images/PassatBW.webp" alt="PassatBW" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Passat Black & White</strong><br><small>B&W Dithering Demo</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/SUVImage.webp" target="_blank">
    <img src="docs/images/SUVImage.webp" alt="SUVImage" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>SUV Image</strong><br><small>SUV Stream Capture</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/SwedishLiveTV.webp" target="_blank">
    <img src="docs/images/SwedishLiveTV.webp" alt="SwedishLiveTV" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Swedish Live TV</strong><br><small>Live TV Stream Demo</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/Tiger.webp" target="_blank">
    <img src="docs/images/Tiger.webp" alt="Tiger" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Tiger</strong><br><small>Tiger Image Demo</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/Volvo240EarlyFLI.webp" target="_blank">
    <img src="docs/images/Volvo240EarlyFLI.webp" alt="Volvo240EarlyFLI" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Volvo 240 Early FLI</strong><br><small>FLI Mode - Volvo 240</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/imageCarBWDither.webp" target="_blank">
    <img src="docs/images/imageCarBWDither.webp" alt="imageCarBWDither" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Car B&W Dither</strong><br><small>B&W Dithering - Car</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/imageCarColorDither.webp" target="_blank">
    <img src="docs/images/imageCarColorDither.webp" alt="imageCarColorDither" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Car Color Dither</strong><br><small>Color Dithering - Car</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/imageVICE.webp" target="_blank">
    <img src="docs/images/imageVICE.webp" alt="imageVICE" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>VICE Emulator</strong><br><small>VICE Emulator Integration</small></p>
</div>

<div style="text-align: center;">
  <a href="docs/images/imageWeb.webp" target="_blank">
    <img src="docs/images/imageWeb.webp" alt="imageWeb" width="280" style="border: 1px solid #ccc; border-radius: 4px;" />
  </a>
  <p><strong>Web Interface</strong><br><small>Web App Interface</small></p>
</div>

</div>

### How to add images:
- Copy image files into docs/images/ (PNG, JPG, GIF, WEBP). Keep file sizes reasonable; optimize for web when possible.
- Commit them on a branch and open a PR. Example Git commands:

  ```bash
  git checkout -b add-docs-images
  mkdir -p docs/images
  cp /path/to/demo1.png docs/images/
  git add docs/images/demo1.png docs/README.md
  git commit -m "docs: add gallery image(s)"
  git push origin add-docs-images
  ```

- For files >100 MB use Git LFS.

Feel free to tell me any images you'd like me to add, or I can open a PR to add real sample images if you upload them here.
