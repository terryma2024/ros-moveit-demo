"""Jazzy spline reconstruction checked against the installed controller library.

This module only reconstructs supplied controller points. It does not establish
an accepted goal interval or authorize a hold after cancellation.
"""
from .contracts import fields,finite,vector

POINT_KEYS=frozenset(('positions','velocities','accelerations'))


def controller_point(point):
    fields(point,POINT_KEYS)
    if not isinstance(point['positions'],(tuple,list)) or not 1<=len(point['positions'])<=6:
        raise ValueError('CONTROLLER_POINT_INVALID')
    count=len(point['positions']);result={'positions':vector(point['positions'],count)}
    for key in ('velocities','accelerations'):
        values=point[key]
        if not isinstance(values,(tuple,list)) or len(values) not in (0,count):raise ValueError('CONTROLLER_POINT_INVALID')
        result[key]=vector(values,count) if len(values) else ()
    return result


def interpolate_segment(begin,first,end,last,at):
    begin,end,at=(finite(v,nonnegative=True) for v in (begin,end,at))
    if not begin<end or not begin<=at<=end:raise ValueError('CONTROLLER_SEGMENT_TIME_INVALID')
    first,last=controller_point(first),controller_point(last)
    if len(first['positions'])!=len(last['positions']):raise ValueError('CONTROLLER_POINT_INVALID')
    duration=end-begin;elapsed=at-begin
    order=0
    if first['velocities'] and last['velocities']:
        order=1
        if first['accelerations'] and last['accelerations']:order=2
    result={k:[] for k in POINT_KEYS}
    for i,(q0,q1) in enumerate(zip(first['positions'],last['positions'],strict=True)):
        delta=q1-q0
        if order==0:
            coefficients=(q0,delta/duration)
        elif order==1:
            v0,v1=first['velocities'][i],last['velocities'][i]
            coefficients=(q0,v0,3*delta/duration**2-(2*v0+v1)/duration,
                -2*delta/duration**3+(v0+v1)/duration**2)
        else:
            v0,v1=first['velocities'][i],last['velocities'][i]
            a0,a1=first['accelerations'][i],last['accelerations'][i]
            coefficients=(q0,v0,a0/2,
                10*delta/duration**3-(6*v0+4*v1)/duration**2-(1.5*a0-.5*a1)/duration,
                -15*delta/duration**4+(8*v0+7*v1)/duration**3+(1.5*a0-a1)/duration**2,
                6*delta/duration**5-3*(v0+v1)/duration**4-(a0-a1)/(2*duration**3))
        result['positions'].append(finite(sum(c*elapsed**j for j,c in enumerate(coefficients))))
        result['velocities'].append(finite(sum(j*c*elapsed**(j-1) for j,c in enumerate(coefficients) if j>=1)))
        result['accelerations'].append(finite(sum(j*(j-1)*c*elapsed**(j-2) for j,c in enumerate(coefficients) if j>=2)))
    return {k:tuple(v) for k,v in result.items()}
