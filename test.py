rows = 10
columns = 5


for i in range(rows*columns):
    reminder = i % columns
    if reminder == 0:
        print(i)
