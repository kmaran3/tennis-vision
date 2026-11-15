import React from 'react';
import * as Select from '@radix-ui/react-select';
import './select.css';

type Props={value:string|number;onChange:(event:{target:{value:string}})=>void;children:React.ReactNode;'aria-label'?:string};
const EMPTY='__baseline_empty__';
const textOf=(node:React.ReactNode):string=>React.Children.toArray(node).map(part=>React.isValidElement<{children:React.ReactNode}>(part)?textOf(part.props.children):String(part)).join('');
export function ThemedSelect({value,onChange,children,'aria-label':label}:Props){
 const options=React.Children.toArray(children).filter(React.isValidElement) as React.ReactElement<{value?:string|number;children:React.ReactNode}>[];
 return <Select.Root value={String(value)||EMPTY} onValueChange={v=>onChange({target:{value:v===EMPTY?'':v}})}>
  <Select.Trigger className="select-trigger" aria-label={label}><Select.Value/><Select.Icon className="select-chevron">⌄</Select.Icon></Select.Trigger>
  <Select.Portal><Select.Content className="select-menu" position="popper" sideOffset={6} collisionPadding={12}>
   <Select.ScrollUpButton className="select-scroll">⌃</Select.ScrollUpButton>
   <Select.Viewport className="select-viewport">{options.map(option=>{const text=textOf(option.props.children);const key=String(option.props.value??text)||EMPTY;return <Select.Item key={key} value={key} className="select-option" textValue={text}><Select.ItemText>{option.props.children}</Select.ItemText><Select.ItemIndicator className="select-check">✓</Select.ItemIndicator></Select.Item>})}</Select.Viewport>
   <Select.ScrollDownButton className="select-scroll">⌄</Select.ScrollDownButton>
  </Select.Content></Select.Portal>
 </Select.Root>;
}
