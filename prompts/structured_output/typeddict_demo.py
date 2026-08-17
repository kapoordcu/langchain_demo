from typing import TypedDict

class Person(TypedDict):

    name: str
    age: int

new_person: Person = {'name':'kapoor', 'age':'42'}

print(new_person)