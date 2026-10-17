import { fireEvent, screen } from '@testing-library/react';
// Radix focuses selected options; jsdom has no scrolling implementation.
HTMLElement.prototype.scrollIntoView ??= ()=>undefined;
export async function chooseSelect(label:string,option:string) {
  fireEvent.keyDown(screen.getByRole('combobox',{name:label}),{key:'ArrowDown'});
  fireEvent.keyDown(await screen.findByRole('option',{name:option}),{key:'Enter'});
}
