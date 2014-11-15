from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.core.paginator import PageNotAnInteger, EmptyPage
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.http import Http404
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.utils.html import format_html

from judge.models import Problem, Submission
from judge.views.submission import ProblemSubmissions
from judge.utils.problems import user_completed_ids, get_result_table
from judge.utils.diggpaginator import DiggPaginator


__all__ = ['RankedSubmissions']


class FancyRawQuerySetWrapper(object):
    def __init__(self, type, count, query, args):
        self._count = count
        self._type = type
        self._query = query
        self._args = args

    def count(self):
        return self._count

    def __getitem__(self, item):
        if isinstance(item, slice):
            offset = item.start
            limit = item.stop - item.start
        else:
            offset = item
            limit = 1
        return list(Submission.objects.raw(self._query + 'LIMIT %s OFFSET %s', self._args + (limit, offset)))


class RankedSubmissions(ProblemSubmissions):
    def get_queryset(self):
        if self.in_contest:
            key = 'contest_problem_rank:%d:%d' % (self.request.user.profile.contest.current.contest_id, self.problem.id)
        else:
            key = 'problem_rank:%d' % self.problem.id
        ranking = cache.get(key)
        if ranking is not None:
            return ranking
        if self.in_contest:
            # WARNING: SLOW
            query = super(RankedSubmissions, self).get_queryset()
            ranking = [query.filter(user_id=user).order_by('-contest__points', 'time', 'memory')
                            .select_related('contest')[0]
                       for user in list(query.values_list('user_id', flat=True).order_by().distinct())]
            ranking.sort(key=lambda sub: (-sub.contest.points, sub.time, sub.memory))
        else:
            ranking = FancyRawQuerySetWrapper(Submission,Submission.objects.filter(problem__id=self.problem.id).filter(
                    Q(result='AC') | Q(problem__partial=True, points__gt=0)).values('user').distinct().count(), '''
                SELECT subs.id, subs.user_id, subs.problem_id, subs.date, subs.time,
                       subs.memory, subs.points, subs.language_id, subs.source,
                       subs.status, subs.result
                FROM (
                    SELECT sub.user_id AS uid, MAX(sub.points) AS points
                    FROM judge_submission AS sub INNER JOIN
                         judge_problem AS prob ON (sub.problem_id = prob.id)
                    WHERE sub.problem_id = %s AND
                         (sub.result = 'AC' OR (prob.partial AND sub.points > 0))
                    GROUP BY sub.user_id
                ) AS highscore INNER JOIN (
                    SELECT sub.user_id AS uid, sub.points, MIN(sub.time) as time
                    FROM judge_submission AS sub INNER JOIN
                         judge_problem AS prob ON (sub.problem_id = prob.id)
                    WHERE sub.problem_id = %s AND
                         (sub.result = 'AC' OR (prob.partial AND sub.points > 0))
                    GROUP BY sub.user_id, sub.points
                ) AS fastest
                        ON (highscore.uid = fastest.uid AND highscore.points = fastest.points)
                    INNER JOIN (SELECT * FROM judge_submission WHERE problem_id = %s) as subs
                        ON (subs.user_id = fastest.uid AND subs.time = fastest.time)
                GROUP BY fastest.uid
                ORDER BY subs.points DESC, subs.time ASC
            ''', (self.problem.id,) * 3)
        cache.set(key, ranking, 86400)
        return ranking

    def get_title(self):
        return 'Best solutions for %s' % self.problem.name

    def get_content_title(self):
        return format_html(u'Best solutions for <a href="{1}">{0}</a>', self.problem.name,
                           reverse('problem_detail', args=[self.problem.code]))

    def get_result_table(self):
        return get_result_table(super(RankedSubmissions, self).get_queryset())
