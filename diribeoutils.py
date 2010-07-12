'''
Created on 08.07.2010

@author: anopheles
'''

from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import Qt

def create_default_image(episode, additional_text = ""):
    multiplikator = 6
    width = 16 * multiplikator
    heigth = 10 * multiplikator
    spacing = 1.25

    #extract text
    text = episode.series[0] + "\n" + episode.get_descriptor() + "\n" + additional_text

    #initalize pixmap object
    pixmap = QtGui.QPixmap(width, heigth)
    pixmap.fill(QtGui.QColor(255,255,255, 0))
    paint = QtGui.QPainter()        
    paint.begin(pixmap)
    paint.setRenderHint(QtGui.QPainter.Antialiasing)        

    #draw background
    gradient = QtGui.QLinearGradient(0, 0, 0, heigth*2)
    backgroundcolor = get_color_shade(episode.descriptor[0], 5)
    comp_backgroundcolor =  get_complementary_color(backgroundcolor)
    gradient.setColorAt(0.0, comp_backgroundcolor.lighter(50))
    gradient.setColorAt(1.0, comp_backgroundcolor.lighter(150))
    paint.setBrush(gradient)
    paint.setPen(QtGui.QPen(QtGui.QColor("black"), 2, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap, QtCore.Qt.RoundJoin))
    paint.drawRoundedRect(QtCore.QRect(spacing, spacing, width-spacing*2, heigth-spacing*2), 20, 15)

    #draw text
    paint.setFont(QtGui.QFont('Arial', 8))
    paint.setPen(QtGui.QColor("black"))
    paint.drawText(QtCore.QRect(spacing, spacing, width-spacing*2, heigth-spacing*2), QtCore.Qt.AlignCenter | QtCore.Qt.TextWordWrap, text)        

    #end painting
    paint.end()

    return pixmap


def get_gradient_background(index, saturation = 0.25):            
    gradient = QtGui.QLinearGradient(0, 0, 0, 200)
    backgroundcolor = get_color_shade(index, 5, saturation)
    comp_backgroundcolor =  get_complementary_color(backgroundcolor)
    gradient.setColorAt(0.0, comp_backgroundcolor.lighter(50))
    gradient.setColorAt(1.0, comp_backgroundcolor.lighter(150))
    return QtGui.QBrush(gradient)


def get_gradient(backgroundcolor, saturation = 0.25):
    gradient = QtGui.QLinearGradient(0, 0, 0, 100)
    gradient.setCoordinateMode(QtGui.QLinearGradient.ObjectBoundingMode)
    gradient.setColorAt(0.0, backgroundcolor.lighter(150))
    gradient.setColorAt(1.0, backgroundcolor.lighter(250))
    return QtGui.QBrush(gradient)

def get_complementary_color(qtcolor):
    h, s, v, a = qtcolor.getHsv()    
    h = (h + 180) % 360     
    return QtGui.QColor.fromHsv(h, s, v, a)


def get_color_shade(index, number_of_colors, saturation = 0.25):      
    return [QtGui.QColor.fromHsvF(colornumber/float(number_of_colors), 1, 0.9, saturation) for colornumber in range(number_of_colors)][index % number_of_colors]