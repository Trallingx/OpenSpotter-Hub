class A:
    def __init__(self):
        pass

    def printer(self):
        print("Hello")


class B:
    def __init__(self):
        pass

    def printer_printer(self):
        method = A()
        method.printer()


add = B()
add.printer_printer()
