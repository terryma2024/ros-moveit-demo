"""Compare reconstruction with the actually installed Jazzy C++ trajectory library."""
import math
from pathlib import Path
import subprocess
import numpy as np
import pytest
from so101_demo.act.trajectory import interpolate_segment


@pytest.fixture(scope='module')
def installed_oracle(tmp_path_factory):
    root=tmp_path_factory.mktemp('installed-jazzy-trajectory')
    src=root/'oracle.cpp'
    src.write_text(r'''
#include <iostream>
#include <iomanip>
#include "joint_trajectory_controller/trajectory.hpp"
int main() {
  joint_trajectory_controller::Trajectory trajectory;
  double duration,at; int a,b;
  while(std::cin>>duration>>at>>a>>b) {
    trajectory_msgs::msg::JointTrajectoryPoint first,second,result;
    for(auto* point : {&first,&second}) {
      for(auto* vector : {&point->positions,&point->velocities,&point->accelerations}) {
        vector->resize(6); for(auto &value:*vector) std::cin>>value;
      }
    }
    if(a<2) first.accelerations.clear(); if(a<1) first.velocities.clear();
    if(b<2) second.accelerations.clear(); if(b<1) second.velocities.clear();
    trajectory.interpolate_between_points(rclcpp::Time(int64_t(1000000000)),first,
      rclcpp::Time(int64_t(1000000000+std::llround(duration*1e9))),second,
      rclcpp::Time(int64_t(1000000000+std::llround(at*1e9))),result);
    std::cout<<std::setprecision(17);
    for(auto* vector : {&result.positions,&result.velocities,&result.accelerations})
      for(double value:*vector) std::cout<<value<<" ";
    std::cout<<"\n";
  }
}
''')
    includes=['-I'+str(p) for p in Path('/opt/ros/jazzy/include').iterdir() if p.is_dir()]
    binary=root/'oracle'
    subprocess.run(['g++','-std=c++17','-O2',*includes,str(src),'-L/opt/ros/jazzy/lib',
        '-Wl,-rpath,/opt/ros/jazzy/lib','-ljoint_trajectory_controller','-lrclcpp',
        '-o',str(binary)],check=True,capture_output=True,text=True)
    return binary


def point(q,v,a,order):
    return dict(positions=tuple(q),velocities=tuple(v) if order>=1 else (),
        accelerations=tuple(a) if order>=2 else ())


def test_linear_cubic_quintic_and_mixed_derivatives_match_installed_controller(installed_oracle):
    rng=np.random.default_rng(20260917);requests=[];cases=[]
    for a in range(3):
      for b in range(3):
       for duration in (.08,.7,1.5):
        vectors=rng.uniform(-.4,.4,(6,6))
        for fraction in (0.,.03,.3,.5,.9,1.):
         at=round(duration*fraction,9)
         requests.append(' '.join(map(str,(duration,at,a,b,*vectors.ravel()))))
         cases.append((duration,at,point(*vectors[:3],a),point(*vectors[3:],b)))
    result=subprocess.run([str(installed_oracle)],input='\n'.join(requests)+'\n',
        capture_output=True,text=True,check=True)
    rows=result.stdout.splitlines();assert len(rows)==len(cases)
    for row,(duration,at,first,last) in zip(rows,cases,strict=True):
        actual=interpolate_segment(1.,first,1.+duration,last,1.+at)
        oracle=np.array([float(x) for x in row.split()]).reshape(3,6)
        assert np.allclose([actual[k] for k in ('positions','velocities','accelerations')],oracle,rtol=1e-9,atol=1e-9)


@pytest.mark.parametrize('change',[
    {'positions':(math.nan,)*6},{'velocities':(.2,)},{'accelerations':(math.inf,)*6},
    {'extra':'truth'},{'positions':()},
])
def test_invalid_controller_points_are_never_reconstructed(change):
    first=point((0.,)*6,(0.,)*6,(0.,)*6,2);last=point((.1,)*6,(0.,)*6,(0.,)*6,2)
    with pytest.raises(ValueError):interpolate_segment(1.,dict(first,**change),2.,last,1.5)


@pytest.mark.parametrize('start,end,at',[(1.,1.,1.),(2.,1.,1.5),(1.,2.,.9),(1.,2.,2.1),(1.,2.,math.nan)])
def test_invalid_segment_time_fails_closed(start,end,at):
    p=point((0.,)*6,(0.,)*6,(0.,)*6,2)
    with pytest.raises(ValueError):interpolate_segment(start,p,end,p,at)
