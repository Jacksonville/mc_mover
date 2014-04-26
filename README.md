MC Mover
========

##Introduction

This program was written to copy files from multiple directories to a single destination while retaining the directory structure and giving the user the flexibility to trim the directories as they see fit.
I was not able to find a free, fast option to accomplish this and so set out to write my own solution.

The file copy is done using the copy2 function from the shutil library, it works quite well and seems to be able to copy at a fairly high rate.
For the gui, pyside is used along with zeromq for communication between threads.

##Dependencies
- pyside>=1.2.1
- zmq

##Usage

The usage of the program is quite straightforward, run the mclub.py file. 
The treeview on the top left shows the source files. Upon selection these files are detailed in the pane on the bottom left. When a destination directory is selected, the bottom right hand panel displays the path of the files when copied.

There are a couple of options for the copy:
- Flatten: This will trim the number of directories from the destination path.
- Overwrite: there are a couple of options here:
 - Newer	: destination files will be overwritten if the source is newer
 - Larger: destination files will be overwritten if the source file is larger
 - Either: will apply either of the above two options.

When the Start copy button is clicked the amount of space is computed and the destination checked to ensure that there is sufficient space available.
If there is not enough space, a dialog will be displayed indicating the amount needed to successfully complete the transfer and the copy halted.

When the copy operation is under-way a progress is displayed that shows the current progress of the operation.

When complete a dialog showing a summary of the operation is displayed.
