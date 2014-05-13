#!/usr/bin/env python

import sys
import os
import platform
import shutil
import zmq
import json
import datetime
from PySide.QtGui import QApplication, QMainWindow, QPixmap, QSplashScreen, QFileSystemModel, QIcon, QFileDialog, QMessageBox, QProgressDialog
from PySide.QtCore import QThread, SIGNAL, Qt

os_version = platform.system()
if os_version == 'Windows':
    import ctypes

from ui_mclub import Ui_MainWindow

__version__ = '1.0.0.0'
zmq_port = 5556


class FileOperations():
    """Class to process file based operations"""
    def __init__(self):
        self.filecount = 0
        self.filelist = []
        self.filesize = 0

    def get_free_space(self, folder):
        """ Return folder/drive free space (in bytes)
        Input:
            folder      : string - Path to folder / drive
        Output:
            returns     : int - Number of bytes available in path
        """
        if os_version == 'Windows':
            free_bytes = ctypes.c_ulonglong(0)
            ctypes.windll.kernel32.GetDiskFreeSpaceExW(ctypes.c_wchar_p(folder), None, None, ctypes.pointer(free_bytes))
            return free_bytes.value
        else:
            st = os.statvfs(folder)
            return st.f_bavail * st.f_frsize

    def get_file_list_for_dir(self, filepath):
        """ Process filepath to det a list of the items.
        Class variables are updated.
        Input:
            filepath    : string - can be either a filepath or directory to be recursively inspected
        Output:
            None"""
        if not os.path.isfile(filepath):
            for r, d, f in os.walk(filepath):
                for file in f:
                    file_path = os.path.join(os.path.abspath(r), file)
                    self.filelist.append(file_path)
                    self.filecount += 1
                    self.get_file_size(file_path)
        else:
            file_path = filepath
            self.filelist.append(file_path)
            self.filecount += 1
            self.get_file_size(file_path)

    def get_file_size(self, filepath, ret=False):
        """Determine size of a file in bytes, results can be returned by setting the ret flag.
        Input:
            filepath    : string - path, must be a file
            ret         : bool  -  if ommited or False class variables will be set, else data will be returned
        Output:
            returns     : int -  number of bytes"""
        try:
            if not ret:
                self.filesize += os.stat(filepath).st_size
            else:
                return os.stat(filepath).st_size
        except:
            self.filesize += 0

    def get_file_age(self, filepath):
        """Determine the age of the file by checking the last modified time.
        Input:
            filepath    : string - can be either a file or directory
        Output:
            returns     : float - number of seconds since epoch, 0 is returned if epoch fails"""
        try:
            fileage = os.path.getmtime(filepath)
            return fileage
        except:
            return 0

    def split_path(self, path):
        """This is used when trimming directories from a path.
        The idea is to split the path into elements then return the reversed list to address the order.
        Input:
            path    : string - the path that you wish to split into a list.
        Output:
            folders : list - the path elements in a list format, ideal for splitting."""
        path = os.path.splitdrive(path)[1][1:]
        folders = []
        while 1:
            path, folder = os.path.split(path)
            if folder != "" and folder:
                folders.append(folder)
                if len(path) == 0:
                    return folders[::-1]
            else:
                if path != "" and path:
                    folders.append(path)
                break
        folders.reverse()
        return folders

    def get_dest_filepath(self, filepath, destpath, flattencount):
        """Determine the flattened filepath for the destination of files.
        Input:
            filepath    : string - the path to the source file.
            destpath    : string - the destination path.
            flattencount: integer- the number of directories to trim from the source path.
        Output:
            dpath       : string - the destination path taking into account the flattencount."""
        fp = self.split_path(filepath)
        if flattencount > 0:
            if len(fp) > flattencount:
                dpath = os.path.abspath(os.path.join(destpath, *fp[flattencount:]))
            else:
                dpath = os.path.abspath(os.path.join(destpath, fp[-1]))
        else:
            dpath = os.path.abspath(os.path.join(destpath, *fp))
        return dpath

    def copy_file_to_dest(self, filepath, destination, overwrite):
        """Copy files to a destination and overwrite / skip based on the overwrite param.
        If the directory is multiple directories, we attempt to create these.
        Input:
            filepath    : string - path to the file you wish to copy.
            destination : string - the path to which you want to copy.
            overwrite   : string - expects 'larger', 'newer' or 'either'
        Output:
            None
        """
        ##TODO: Find a way to return the errors to the caller and show the user.
        source_filesize = self.get_file_size(filepath, True)
        source_fileage = self.get_file_age(filepath)
        if os.path.exists(destination):
            dest_filesize = self.get_file_size(destination, True)
            dest_fileage = self.get_file_age(destination)
            if overwrite == 'larger':
                if source_filesize > dest_filesize:
                    copy_file_flag = True
            elif overwrite == 'newer':
                if source_fileage > dest_fileage:
                    copy_file_flag = True
            elif overwrite == 'either':
                copy_file_flag = True
            else:
                copy_file_flag = False
        else:
            copy_file_flag = True
        if copy_file_flag:
            destdir = os.path.split(destination)[0]
            if not os.path.exists(destdir):
                try:
                    os.makedirs(destdir)
                except:
                    print(("Unable to create %s" % destdir))
            try:
                shutil.copy2(filepath, destination)
            except:
                print(("Error encountered while copying %s to %s" % (filepath, destination)))
            else:
                self.filesize += source_filesize
                self.filecount += 1


class CopyWorker(QThread):
    "Worker thread for the filecopy operation to prevent the GUI from hanging."
    def __init__(self, parent=None):
        super(CopyWorker, self).__init__(parent)
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PAIR)
        self.socket.connect("tcp://localhost:%s" % zmq_port)
        self.must_run = True

    def run(self):
        msg = self.socket.recv()
        paramdict = json.loads(msg)
        self.pathlist = paramdict['filelist']
        self.destdir = paramdict['destdir']
        self.flattencount = paramdict['flattencount']
        self.overwrite = paramdict['overwrite_opt']
        dirstat = FileOperations()
        available_space = dirstat.get_free_space(self.destdir)
        filecount = 0
        filesize = 0
        filelist = []
        for filepath in self.pathlist:
            fileop = FileOperations()
            fileop.get_file_list_for_dir(filepath)
            filecount += fileop.filecount
            filelist.extend(fileop.filelist)
            filesize += fileop.filesize
        if filesize < available_space:
            self.emit(SIGNAL("copyProgress(QString, QString, QString)"), '0', '0', "%s" % filecount)
            start_time = datetime.datetime.now()
            filecopy = FileOperations()
            for file in sorted(set(filelist)):
                if self.must_run:  # Check if cancel has been toggled
                    destfilepath = filecopy.get_dest_filepath(file, self.destdir, self.flattencount)
                    filecopy.copy_file_to_dest(file, destfilepath, self.overwrite)
                    progress_percent = int((float(filecopy.filesize) / float(filesize)) * 100)
                    print (('Progress Percent:\t%s\nFilecopied:\t%s\nTotalFilesize:\t%s' % (progress_percent, filecopy.filesize, filesize)))
                    print ((float(filecopy.filesize) / float(filesize)))
                    if self.must_run:
                        self.emit(SIGNAL("copyProgress(QString, QString, QString)"),
                                         '%s' % progress_percent, "%s" % filecopy.filecount, "%s" % filecount)
                else:
                    print ('Copy cancelled')
                    return
        else:
            self.emit(SIGNAL('spaceProblem(int, int)'), filesize, available_space)
            return
        end_time = datetime.datetime.now()
        runtime = end_time - start_time
        if filesize > 0:
            filesize = filesize / 1024.00 / 1024.00 / 1024.00
        self.emit(SIGNAL("copyComplete(QString, QString, QString, QString)"),
                         '%s' % filecount, "%f" % filesize, "%s" % runtime, "%s" % runtime.total_seconds())


class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent)
        self.setupUi(self)
        self.build_dir_tree()
        self.setWindowIcon(QIcon('favicon.png'))
        self.actionAbout.triggered.connect(self.about)
        self.destButton.clicked.connect(self.destination_chooser)
        self.actionChoose_Destination.triggered.connect(self.destination_chooser)
        self.copyButton.clicked.connect(self.copy_files)
        self.actionStart_Copy.triggered.connect(self.copy_files)
        self.ckbxTrimDir.toggled.connect(self.update_table_view)
        self.treeView.expanded.connect(self.resize_tree_column)
        self.treeView.collapsed.connect(self.resize_tree_column)
        self.treeView.clicked.connect(self.update_table_view)
        self.trimdirCount.valueChanged.connect(self.update_table_view)

        self.listWidget.doubleClicked.connect(self.unselectItem)

        self.copyButton.setEnabled(False)
        self.lblTrimDir.setVisible(False)
        self.trimdirCount.setVisible(False)
        self.rbOWNewer.setVisible(False)
        self.rbOWLarger.setVisible(False)
        self.rbOWEither.setVisible(False)
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PAIR)
        self.socket.bind("tcp://*:%s" % zmq_port)

        self.copyWorker = CopyWorker()
        self.connect(self.copyWorker, SIGNAL("copyComplete(QString, QString, QString, QString)"), self.copy_complete, Qt.QueuedConnection)
        self.connect(self.copyWorker, SIGNAL("spaceProblem(int, int)"), self.space_problem, Qt.QueuedConnection)

    def unselectItem(self, item):
        ##need to figure out how to remove from the model
        self.listWidget.takeItem(item.row())

    def copy_complete(self, filecount, filesize, runtime, run_seconds):
        self.progress.setValue(self.progress.maximum())
        transfer_rate = round((float(filesize) * 1024) / float(run_seconds), 3)
        filesize = round(float(filesize), 3)
        QMessageBox.information(self, "File Copy Complete",
            """Your file copy has been successfully completed.\n
            Files processed:\t%s\n
            Data copied:\t%sGB\n
            Total runtime:\t%s\n
            Transfer Rate:\t%sMB/Sec""" % (filecount, filesize, runtime, transfer_rate),
            WindowModility=True)
        self.copyButton.setEnabled(True)

    def space_problem(self, dirsize, filesize):
        """Display a dialog to the user advising that there is not enough space in the destination
        directory.
        Input:
            dirsize :   integer - amount of space available in the destination directory
            filesize:   integer - size of the selected files
        Output:
            None, dialog is displayed to the user."""
        ##TODO: Set the messagebox modal property to true
        required_space = (filesize / 1024.00 / 1024.00 / 1024.00) - (dirsize / 1024.00 / 1024.00 / 1024.00)
        QMessageBox.critical(self,
                             "Not enough space",
                             """You do not have enough space in your selected destination to complete this operation\n
                             %s more GB space required""" % required_space,
                             WindowModility=True)
        self.copyWorker.quit()
        self.copyButton.setEnabled(True)

    def build_dir_tree(self):
        """Add a directory tree listing to the QTreeView and set the root
        to the drive that it was run from.
        Input:
            None
        Output:
            None"""
        ##TODO: add linux support for the model root drive.
        self.model = QFileSystemModel(self)
        if sys.platform == 'win32':
            self.model.setRootPath(os.path.splitdrive(os.getcwd())[0])
        self.tree = self.treeView
        self.tree.setModel(self.model)
        self.tree.setAnimated(False)
        self.tree.setIndentation(20)
        self.tree.setSortingEnabled(True)

    def update_table_view(self):
        """Refresh listview with selected items in the treeView using
        the shared model.
        Input:
            None
        Output:
            None"""
        itemlist = [os.path.abspath(
            self.model.filePath(
                self.model.index(selection.row(),
                    0,
                    selection.parent()
                    )
                )
            )
            for selection in self.treeView.selectedIndexes()]
        self.listWidget.clear()
        self.listWidget.addItems(itemlist)

        nitemlist = []
        fileops = FileOperations()
        if not self.ckbxTrimDir.isChecked():
            flattencount = 0
        else:
            flattencount = self.trimdirCount.value()
        if self.lblDestPath.isEnabled():
            self.previewView.clear()
            for item in itemlist:
                nitemlist.append(fileops.get_dest_filepath(item, self.lblDestPath.text(), flattencount))
            self.previewView.addItems(nitemlist)
        else:
            self.previewView.clear()
            self.previewView.addItems(['No destination folder selected'])

        self.resize_tree_column()

    def resize_tree_column(self):
        """Resize the treeView column to fit the contents.
        Input:
            None
        Output:
            None"""
        self.treeView.resizeColumnToContents(0)

    def copy_files(self):
        """Initiate copy process. File size is calculated first to
        check that there is enough space in the destination.
        If there is enough space then we start the copy of the files
        to their destination.
        Input:
            None
        Output:
            None"""
        self.copyButton.setEnabled(False)
        self.copyWorker.must_run = True
        self.connect(self.copyWorker, SIGNAL("copyProgress(QString, QString, QString)"), self.copy_progress, Qt.QueuedConnection)
        dest_dir = self.lblDestPath.text()
        if dest_dir == '':
            QMessageBox.critical(self, "Destination not set", "Please specify a destination path", WindowModility=True)
        else:
            copy_filelist = []
            for selection in self.treeView.selectedIndexes():
                indexItem = self.model.index(selection.row(), 0, selection.parent())
                copy_filelist.append(self.model.filePath(indexItem))
            if self.cbOWDest.isChecked():
                if self.rbOWEither.isChecked():
                    overwrite_option = 'either'
                elif self.rbOWLarger.isChecked():
                    overwrite_option = 'larger'
                elif self.rbOWNewer.isChecked():
                    overwrite_option = 'newer'
                else:
                    QMessageBox.critical(self,
                        "Overwrite option missing",
                        """You did not select an overwrite option.""",
                        WindowModility=True)
                    self.copyButton.setEnabled(True)
                    return
            else:
                overwrite_option = None
            if not self.ckbxTrimDir.isChecked():
                flattencount = 0
            else:
                flattencount = self.trimdirCount.value()

            self.progress = QProgressDialog("Copy in progress.", "Cancel", 0, 100, modal=True)
            self.progress.canceled.connect(self.cancel_copy)
            self.progress.setWindowTitle('Copy Progress')
            var_values = {'destdir': dest_dir, 'filelist': copy_filelist, 'flattencount': flattencount, 'overwrite_opt': overwrite_option}
            self.socket.send(json.dumps(var_values))
            self.copyWorker.start()

    def copy_progress(self, percentage_complete, filecount, filecomplete):
        """Display the progress bar with a completed percentage.
        Input:
            percentage_complete :   integer - the amount complete in percent.
            filecount           :   integer - the total number of files being processed.
            filecomplete        :   integer - the number of files that have already been processed.
        Output:
            None, dialog is updated"""
        ##TODO: display the current transfer rate
        ##TODO: display the current file being transferred and possibly the progress thereof.
        ##Perhaps use the statusbar method for this
        self.progress.setValue(int(percentage_complete))

    def cancel_copy(self):
        """Slot for the cancel command on the progress dialog.
        The must_run variable of the copyWorker class is set to False to terminate the copy.
        Input:
            None
        Output:
            None"""
        self.copyWorker.must_run = False
        self.copyButton.setEnabled(True)

    def statusbar_msg(self, msg):
        """Update the statusbar on the bottom of the screen.
        Input:
            msg     : string - Message that you would like displayed on the form.
        Output:
            None
        """
        self.statusbar.clearMessage()
        self.statusbar.showMessage(msg)

    def destination_chooser(self):
        """Show folder chooser dialog and update lblDestPath with path selected.
        Input:
            None
        Output:
            None"""
        dialog = QFileDialog()
        dialog.setFileMode(QFileDialog.Directory)
        dialog.setOption(QFileDialog.ShowDirsOnly)
        dialog.exec_()
        self.lblDestPath.setEnabled(True)
        self.lblDestPath.setText(os.path.abspath(dialog.directory().absolutePath()))
        self.update_table_view()
        self.copyButton.setEnabled(True)

    def about(self):
        """Popup a box with about message.
        Input:
            None
        Output:
            None"""
        QMessageBox.about(self, "About MClub Mover",
                """This program is designed to help make the process of copying \
files from multiple directories much easier and simpler.\n
This software is provided as is with absolutely no warranties.""",
                WindowModility=True)

if __name__ == '__main__':
    ##TODO: Look into setting caching to remember a users preference from previous execution
    if os_version == 'Windows':  # Uberhack to make windows show my icon in the taskbar
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('mclub.mover.%s' % __version__)
    app = QApplication(sys.argv)
    splash_img = QPixmap('splash.png')
    splash = QSplashScreen(splash_img)  # Need to see how to cleanly destroy the splash once the form is loaded.
    splash.show()
    frame = MainWindow()
    frame.show()
    app.setWindowIcon(QIcon('favicon.png'))
    app.exec_()