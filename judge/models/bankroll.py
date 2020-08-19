from django.db import models
from judge.models.problem import Problem
from judge.models.profile import Profile

class Bankroll(models.Model):

    class Meta:
        unique_together = (('user', 'date'),)

    # NOTE models.CASCADE also delete the objects that have references to it
    user = models.ForeignKey(Profile, on_delete=models.CASCADE)
    date = models.DateTimeField(default=None)
    cash = models.FloatField(default=-1)
    cash_invested = models.FloatField(default=-1)