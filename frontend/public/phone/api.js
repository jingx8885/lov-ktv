/** @type {PhoneApi} */
export const api = /** @type {PhoneApi} */ ({});

/** @param {PhoneApi} bag */
export function installApi(bag) {
  Object.assign(api, bag);
}
