export function Surface({ as: Element = "div", level = "surface", className = "", children, ...props }) {
  return (
    <Element className={`surface surface--${level} ${className}`.trim()} {...props}>
      {children}
    </Element>
  );
}

export function Divider({ className = "" }) {
  return <div aria-hidden="true" className={`divider ${className}`.trim()} />;
}
