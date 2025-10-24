import { writeFileSync, existsSync } from 'fs';

export function writeFile(path: string, value: string|Object) {
  if(!value) {
    throw new Error('path must be provided')
  }

  if(!existsSync(path)) {
    return
  }

  if(!value) {
    throw new Error('value must be provided')
  }

  let writeValue: string
  switch(typeof value) {
    case 'object':
      writeValue = JSON.stringify(value, null, 2)
      break
    default:
      writeValue = value
  }
  

  writeFileSync(path, writeValue, { encoding: 'utf-8' });
}