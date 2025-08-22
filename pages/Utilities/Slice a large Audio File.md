---
date: '2025-07-26T03:01:29'
title: Slice a large Audio File
---

The command:<BR> 
**ffmpeg -i input_filename.m4a -f segment -segment_time 600 -c copy output_%03d.m4a**

Brief explanation:<BR>
**-i input_filename.m4a**  ( the m4a file to be split up) <BR>
**-f segment** (segment the file)<BR>
**-segment_time 600** (make each segment 600 seconds long)<BR>
**-c copy output_%03d.m4a**  ( each segment file starts with "output_" and has a 3 digit sequence number appended)<BR>