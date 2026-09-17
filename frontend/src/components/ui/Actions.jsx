import { motion, useReducedMotion } from "motion/react";
import { ArrowRightIcon } from "../icons/Icons.jsx";

function actionMotion(reducedMotion) {
  return reducedMotion
    ? undefined
    : {
        whileHover: { y: -1 },
        whileTap: { y: 1 },
        transition: { duration: 0.16, ease: [0.22, 1, 0.36, 1] },
      };
}

export function PrimaryAction({ children, href, className = "", ...props }) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.a
      className={`button button--primary ${className}`.trim()}
      href={href}
      {...actionMotion(reducedMotion)}
      {...props}
    >
      <span>{children}</span>
      <ArrowRightIcon className="button__arrow" />
    </motion.a>
  );
}

export function SecondaryAction({ children, href, className = "", ...props }) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.a
      className={`button button--secondary ${className}`.trim()}
      href={href}
      {...actionMotion(reducedMotion)}
      {...props}
    >
      <span>{children}</span>
      <ArrowRightIcon className="button__arrow" />
    </motion.a>
  );
}

export function EditorialLink({ children, href, className = "", ...props }) {
  return (
    <a className={`motion-link editorial-link ${className}`.trim()} href={href} {...props}>
      <span>{children}</span>
      <ArrowRightIcon className="motion-link__arrow" size={14} />
    </a>
  );
}

export function IconButton({ label, children, className = "", ...props }) {
  return (
    <button
      aria-label={label}
      className={`icon-button ${className}`.trim()}
      type="button"
      {...props}
    >
      {children}
    </button>
  );
}
