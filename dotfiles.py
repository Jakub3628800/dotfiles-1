import py
import os
import click
import errno
from operator import attrgetter


DEFAULT_HOMEDIR = os.path.expanduser('~/')
DEFAULT_REPO_PATH = os.path.expanduser('~/Dotfiles')
DEFAULT_REPO_IGNORE = ['.git', '.gitignore']


class DotfileException(Exception):
    """An exception the CLI can handle and show to the user."""

    def __init__(self, message):
        Exception.__init__(self, message)
        self.message = message

    def __str__(self):
        return 'Error: %s' % self.message


class TargetIgnored(DotfileException):

    def __init__(self, path):
        message = '%s targets an ignored file' % path.basename
        DotfileException.__init__(self, message)


class IsDirectory(DotfileException):

    def __init__(self, path):
        message = '%s is a directory' % path.basename
        DotfileException.__init__(self, message)


class InRepository(DotfileException):

    def __init__(self, path):
        message = '%s is within the repository' % path.basename
        DotfileException.__init__(self, message)


class NotRootedInHome(DotfileException):

    def __init__(self, path):
        message = '%s is not rooted in the home directory' % path.basename
        DotfileException.__init__(self, message)


class IsNested(DotfileException):

    def __init__(self, path):
        message = '%s is nested' % path.basename
        DotfileException.__init__(self, message)


class NotADotfile(DotfileException):

    def __init__(self, path):
        message = '%s is not a dotfile' % path.basename
        DotfileException.__init__(self, message)


class Repository(object):
    """A repository is a directory that contains dotfiles.

    :param repodir: the location of the repository directory
    :param homedir: the location of the home directory (primarily for testing)
    :param ignore:  a list of targets to ignore
    """

    def __init__(self, repodir, homedir, ignore=[]):
        self.ignore = ignore
        self.homedir = homedir

        # create repository if needed
        self.repodir = repodir.ensure(dir=1)

    def __str__(self):
        """Return human-readable repository contents."""
        return ''.join('%s\n' % item for item in self.contents()).rstrip()

    def __repr__(self):
        return '<Repository %r>' % self.repodir

    def _target_to_name(self, target):
        """Return the expected symlink for the given repository target."""
        return self.homedir.join('.%s' % target.basename)

    def _name_to_target(self, name):
        """Return the expected repository target for the given symlink."""
        return self.repodir.join(name.basename[1:])

    def dotfile(self, name):
        """Return a valid dotfile for the given path."""

        target = self._name_to_target(name)
        if target.basename in self.ignore:
            raise TargetIgnored(name)

        if name.check(dir=1):
            raise IsDirectory(name)

        for path in name.parts():
            try:
                if self.repodir.samefile(path):
                    raise InRepository(name)
            except py.error.ENOENT:
                # this occurs when the symlink does not yet exist
                continue

        if not self.homedir.samefile(name.dirname):
            raise NotRootedInHome(name)

        if name.dirname != self.homedir:
            raise IsNested(name)

        if name.basename[0] != '.':
            raise NotADotfile(name)

        return Dotfile(name, target)

    def dotfiles(self, path):
        """Return a list of dotfiles given a path."""

        if path.check(dir=1):
            raise IsDirectory(path)

        return self.dotfile(path)

    def contents(self):
        """Return a list of all dotfiles in the repository path."""
        contents = []
        for target in self.repodir.listdir():
            target = py.path.local(target)
            if target.basename not in self.ignore:
                contents.append(Dotfile(self._target_to_name(target), target))
        return sorted(contents, key=attrgetter('name'))


class Dotfile(object):
    """An configuration file managed within a repository.

    :param name:   name of the symlink in the home directory (~/.vimrc)
    :param target: where the symlink should point to (~/Dotfiles/vimrc)
    """

    def __init__(self, name, target):
        self.name = name
        self.target = target

    def __str__(self):
        return self.name.basename

    def __repr__(self):
        return '<Dotfile %r>' % self.name

    def _add(self, verbose):
        if verbose:
            click.echo('MOVE   %s -> %s' % (self.name, self.target))
        self.name.move(self.target)
        # self._link(verbose)
        self.link(verbose)

    def _remove(self, verbose):
        # self._unlink(verbose)
        self.unlink(verbose)
        if verbose:
            click.echo('MOVE   %s -> %s' % (self.target, self.name))
        self.target.move(self.name)

    def _link(self, verbose):
        if verbose:
            click.echo('LINK   %s -> %s' % (self.name, self.target))
        self.name.mksymlinkto(self.target, absolute=0)

    def _unlink(self, verbose):
        if verbose:
            click.echo('REMOVE %s' % self.name)
        self.name.remove()

    @property
    def state(self):
        if self.target.check(exists=0):
            # only for testing, cli should never reach this state
            return 'error'
        elif self.name.check(exists=0):
            # no $HOME symlink
            return 'missing'
        elif self.name.check(link=0) or not self.name.samefile(self.target):
            # if name exists but isn't a link to the target
            return 'conflict'
        return 'ok'

    # TODO: update below exceptions

    def add(self, verbose=False):
        if self.name.check(file=0):
            raise Exception('%s is not a file' % self.name.basename)
        if self.target.check(exists=1):
            raise OSError(errno.EEXIST, self.target)
        self._add(verbose)

    def remove(self, verbose=False):
        if not self.name.check(link=1):
            raise Exception('%s is not a symlink' % self.name.basename)
        if self.target.check(exists=0):
            raise OSError(errno.ENOENT, self.target)
        self._remove(verbose)

    def link(self, verbose=False):
        if self.name.check(exists=1):
            raise OSError(errno.EEXIST, self.name)
        if self.target.check(exists=0):
            raise OSError(errno.ENOENT, self.target)
        self._link(verbose)

    def unlink(self, verbose=False):
        if self.name.check(link=0):
            raise Exception('%s is not a symlink' % self.name.basename)
        if self.target.check(exists=0):
            raise Exception('%s does not exist' % self.target)
        if not self.name.samefile(self.target):
            raise Exception('good lord')
        self._unlink(verbose)


pass_repo = click.make_pass_decorator(Repository)


@click.group(context_settings=dict(help_option_names=['-h', '--help']))
@click.option('--repository', type=click.Path(), show_default=True,
              default=DEFAULT_REPO_PATH)
@click.version_option()
@click.pass_context
def cli(ctx, repository):
    """Dotfiles is a tool to make managing your dotfile symlinks in $HOME easy,
    allowing you to keep all your dotfiles in a single directory.
    """
    ctx.obj = Repository(py.path.local(repository),
                         py.path.local(DEFAULT_HOMEDIR),
                         DEFAULT_REPO_IGNORE)


@cli.command()
@click.option('-v', '--verbose', is_flag=True, help='Show executed commands.')
@click.argument('files', nargs=-1, type=click.Path(exists=True))
@pass_repo
def add(repo, verbose, files):
    """Replace file with symlink."""
    for filename in files:
        try:
            repo.dotfile(py.path.local(filename)).add(verbose)
        except DotfileException as err:
            click.echo(err)


@cli.command()
@click.option('-v', '--verbose', is_flag=True, help='Show executed commands.')
@click.argument('files', nargs=-1, type=click.Path(exists=True))
@pass_repo
def remove(repo, verbose, files):
    """Replace symlink with file."""
    for filename in files:
        repo.dotfile(py.path.local(filename)).remove(verbose)


@cli.command()
@click.option('-v', '--verbose', is_flag=True, help='Show all dotfiles.')
@click.option('-c', '--color',   is_flag=True, help='Enable color output.')
@pass_repo
def status(repo, verbose, color):
    """Show all dotfiles in a non-OK state."""

    state_info = {
        'error':    {'char': 'E', 'color': None},
        'conflict': {'char': '!', 'color': None},
        'missing':  {'char': '?', 'color': None},
    }

    if verbose:
        state_info['ok'] = {'char': ' ', 'color': None}

    if color:
        state_info['error']['color'] = 'red'
        state_info['conflict']['color'] = 'magenta'
        state_info['missing']['color'] = 'yellow'

    for dotfile in repo.contents():
        try:
            char = state_info[dotfile.state]['char']
            fg = state_info[dotfile.state]['color']
            click.secho('%c %s' % (char, dotfile), fg=fg)
        except KeyError:
            continue


@cli.command()
@click.option('-v', '--verbose', is_flag=True, help='Show executed commands.')
@click.argument('files', nargs=-1, type=click.Path())
@pass_repo
def link(repo, verbose, files):
    """Create missing symlinks."""
    for filename in files:
        repo.dotfile(py.path.local(filename)).link(verbose)


@cli.command()
@click.option('-v', '--verbose', is_flag=True, help='Show executed commands.')
@click.argument('files', nargs=-1, type=click.Path(exists=True))
@pass_repo
def unlink(repo, verbose, files):
    """Remove existing symlinks."""
    for filename in files:
        repo.dotfile(py.path.local(filename)).unlink(verbose)