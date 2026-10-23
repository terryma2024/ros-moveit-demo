// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { expect,test } from 'vitest';
import { SignalChart } from './signal-chart';
import { seriesData } from './test-fixtures';
test('downsampled signals retain actual dimensions and exact intermediate row cursor time',()=>{
  const {rerender}=render(<SignalChart points={seriesData.points} group="state" currentRow={2} currentTime={36.4}/>);
  expect(screen.getByRole('img',{name:'state signals'}).querySelectorAll('polyline')).toHaveLength(8);
  const cursor=screen.getByTestId('signal-cursor');expect(cursor.getAttribute('data-time')).toBe('36.4');
  expect(Number(cursor.getAttribute('x1'))).toBeCloseTo(320);
  rerender(<SignalChart points={seriesData.points} group="action" currentRow={4} currentTime={36.6}/>);
  expect(screen.getByRole('img',{name:'action signals'}).querySelectorAll('polyline')).toHaveLength(6);
});
