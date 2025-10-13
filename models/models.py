from mongoengine import Document, StringField, IntField, DateTimeField


class Card(Document):
    hotel_id = IntField(required=True)
    card_no = IntField(required=True, unique=True)
    checkin_time = DateTimeField(required=True)
    checkout_time = DateTimeField(required=True)
    room_no = StringField(required=True)
    card_hex = StringField(required=True)

    def __str__(self):
        return f"Card {self.card_no} for Room {self.room_no} at Hotel {self.hotel_id}"