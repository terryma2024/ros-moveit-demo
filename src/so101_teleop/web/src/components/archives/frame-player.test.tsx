// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { ArchivesApiClient } from '@/api/archives-client';
import { FramePlayer } from './frame-player';
const api=new ArchivesApiClient();
afterEach(()=>{vi.useRealTimers();});
function Player(){const [row,setRow]=useState(0);return <FramePlayer api={api} packageId="p" sceneId="s" frameCount={5} row={row} onRowChange={setRow} rowTimes={[1,2,3,4,5]}/>;}

test('play advances at 10Hz, pauses at final row and cleans up on unmount',()=>{
  vi.useFakeTimers();const {unmount}=render(<Player/>);
  fireEvent.click(screen.getByRole('button',{name:'Play'}));
  for(let i=0;i<4;i++) act(()=>vi.advanceTimersByTime(100));
  expect(screen.getByRole('slider').getAttribute('aria-valuenow')).toBe('4');
  expect(screen.getByRole('button',{name:'Play'})).toBeTruthy();
  unmount();expect(vi.getTimerCount()).toBe(0);
});

test('only next two rows per camera prefetch and image failure is visible',()=>{
  const srcs:string[]=[];
  const ImageOriginal=globalThis.Image;
  class Prefetch {set src(value:string){srcs.push(value);} removeAttribute(){} }
  vi.stubGlobal('Image',Prefetch);
  try {
    render(<Player/>);expect(srcs).toHaveLength(4);
    expect(srcs.every(src=>/frames\/[12]\//.test(src))).toBe(true);
    fireEvent.error(screen.getByAltText('head camera'));
    expect(screen.getByText(/head frame unavailable/)).toBeTruthy();
  } finally {vi.stubGlobal('Image',ImageOriginal);}
});

test('empty fault data has no playback controls',()=>{
  render(<FramePlayer api={api} packageId="p" sceneId="fault" frameCount={0} row={0} onRowChange={()=>undefined} rowTimes={[]}/>);
  expect(screen.queryByRole('slider')).toBeNull();
  expect(screen.getByText(/No recorded frames/)).toBeTruthy();
});

test('a single recorded frame has a disabled slider with a finite thumb position',()=>{
  const onRowChange=vi.fn();
  render(<FramePlayer api={api} packageId="p" sceneId="one" frameCount={1} row={0} onRowChange={onRowChange} rowTimes={[1]}/>);
  const slider=screen.getByRole('slider',{name:'Episode row'});
  expect(slider.getAttribute('aria-valuemax')).toBe('0');
  expect(slider.parentElement!.outerHTML).not.toContain('NaN');
  fireEvent.keyDown(slider,{key:'End'});
  expect(onRowChange).not.toHaveBeenCalled();
});
