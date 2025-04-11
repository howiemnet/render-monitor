# render-monitor
UDP based render farm monitor.

Simple activity monitor for my LAN. Using a script on each node, and one on a machine acting as a "server" - though it can be any machine on the LAN - this setup gathers CPU and GPU activity data from the nodes on my network, and serves a simple webpage to let me see the state of things. 

Key feature for me is that it lets me see activity of both my Linux render nodes (usually running Houdini or Blender) *and* my Mac (which may be using AE, Fusion, Resolve, or ffmpeg) - so I can see quickly if a machine has hung, or if things have finished.

Other key feature: because the data is presented as a webpage, I can monitor things with any machine or device on my network - my phone, say, or this portable "Raspberry PI jammed into a skinny AliExpress LCD monitor" gizmo:

https://github.com/howiemnet/render-monitor/blob/main/images/WhatsApp%20Image%202025-04-09%20at%2009.52.21%20(1).jpeg

h / 2025-04-11
