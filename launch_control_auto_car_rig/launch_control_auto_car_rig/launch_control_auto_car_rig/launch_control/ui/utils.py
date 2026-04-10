import bpy
from textwrap import TextWrapper

def show_message_box(message="", title="Message Box", icon="INFO"):
    def draw(self, context):
        self.layout.label(text=message)
    
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)


def show_message_box_multiline(lines="", title = "Message Box", icon = 'INFO'):
    myLines=lines
    def draw(self, context):
        for n in myLines:
            row = self.layout.row()
            row.label(text=n)
            row.enabled = False
    bpy.context.window_manager.popup_menu(draw, title = title, icon = icon)


def label_multiline(context, text, parent, icon="NONE"):
    chars = int(context.region.width / 7)   # 7 pix on 1 character
    wrapper = TextWrapper(width=chars)
    text_lines = wrapper.wrap(text=text)
    first = True
    for text_line in text_lines:
        if first:
            parent.label(text=text_line, icon=icon)
            first = False
        else:
            parent.label(text=text_line)
            