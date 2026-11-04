"""Small authored line icons, rendered by Qt; no network/font icon dependency."""
from PySide6.QtCore import QByteArray, QSize, QRectF, Qt
from PySide6.QtGui import QIcon, QPixmap, QPainter, QImageReader
from PySide6.QtSvg import QSvgRenderer

PATHS = {
 'New':'<path d="M12 5v14M5 12h14"/>',
 'Open':'<path d="M3 8V5h6l2 3h10l-3 11H3z"/><path d="M3 10h17"/>',
 'Save':'<path d="M4 3h14l3 3v15H3V3z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
 'Revise':'<path d="m4 17-1 4 4-1L20 7l-3-3zM14 7l3 3"/>',
 'Settings':'<path d="M4 7h16M4 17h16"/><circle cx="9" cy="7" r="3"/><circle cx="15" cy="17" r="3"/>',
 'Publish':'<path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6"/>',
 'Activity':'<path d="M3 12h4l3-7 4 14 3-7h4"/>',
 'Page':'<path d="M5 2h9l5 5v15H5zM14 2v6h5M8 12h8M8 16h6"/>',
 'Arrow':'<path d="M4 12h16m-6-6 6 6-6 6"/>',
 'Code':'<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-5-1 2-10"/>',
 'Canvas':'<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 8h18M8 8v13"/>',
}


def icon(name, color='#acb5c8', size=20):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"><g fill="none" stroke="'+color+'" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'+PATHS.get(name,PATHS['Page'])+'</g></svg>'
    pix = QPixmap(size*2,size*2)
    pix.fill(Qt.GlobalColor.transparent)
    pix.setDevicePixelRatio(2)
    painter = QPainter(pix)
    QSvgRenderer(QByteArray(svg.encode())).render(painter,QRectF(0,0,size,size))
    painter.end()
    return QIcon(pix)


def thumbnail(path):
    reader = QImageReader(str(path))
    reader.setScaledSize(QSize(56,56))
    image = reader.read()
    return QIcon(QPixmap.fromImage(image)) if not image.isNull() else icon('Page')
