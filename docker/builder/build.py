#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import string
import subprocess
import os
import argparse
import logging
import sys
from typing import Dict, Union

IMAGE = "harbor.internal.moqi.ai/mqdb/builder"
BUILDER = "/builder"
VERSION_FILE = "cmake/autogenerated_versions.txt"

BUILDER_SCRIPT = os.path.realpath(__file__)
BUILDER_DIRECTORY = os.path.dirname(BUILDER_SCRIPT)
BUILDER_DOCKERFILE = os.path.join(BUILDER_DIRECTORY, "Dockerfile")
BUILDER_PROFILE_DIRECTORY = os.path.join(BUILDER_DIRECTORY, "profile.d")
BUILDER_PACKAGE_DIRECTORY = os.path.join(BUILDER_DIRECTORY, "package.d")
WORK_DIRECTORY = os.path.abspath(os.path.join(os.path.dirname(BUILDER_SCRIPT), os.pardir, os.pardir))
WORK_DIRECTORY_NAME = os.path.basename(WORK_DIRECTORY)
BUILD_DIRECTORY = os.path.join(WORK_DIRECTORY, "build")


def command(cmd, shell=False, cwd=None, env=None) -> int:
    logging.info("Run command: %s", cmd)
    return subprocess.check_call(cmd, shell=shell, cwd=cwd, env=env)


def check_image_exists_locally(image: str):
    cmd = f"docker images -q {image} 2> /dev/null"
    logging.info("Run command: %s", cmd)
    try:
        output = subprocess.check_output(cmd, shell=True)
        return output != ""
    except subprocess.CalledProcessError:
        return False


def pull_image(image: str):
    cmd = f"docker pull {image}"
    logging.info("Run command: %s", cmd)
    try:
        subprocess.check_call(cmd, shell=True)
        return True
    except subprocess.CalledProcessError:
        logging.info(f"Cannot pull image {image}".format())
        return False


def build_image(image: str, filepath: str):
    context = os.path.dirname(filepath)
    cmd = f"docker build --rm=true -t {image} -f {filepath} {context}"
    command(cmd, shell=True, cwd=WORK_DIRECTORY)


def run_docker_builder(image: str, as_root: bool, ccache: str, output: str, args: list):
    if sys.stdout.isatty():
        interactive = "-it"
    else:
        interactive = ""

    if as_root:
        user = "0:0"
    else:
        user = f"{os.geteuid()}:{os.getegid()}"

    build = "docker/builder/build.py"
    cmd = (f"docker run --user={user} --hostname builder --rm --workdir {BUILDER}/{WORK_DIRECTORY_NAME} --volume={output}:{BUILDER}/output "
           f"--volume={WORK_DIRECTORY}:{BUILDER}/{WORK_DIRECTORY_NAME} --volume={ccache}:{BUILDER}/.ccache "
           f"{interactive} {image} {build} {' '.join(args)}")

    return command(cmd, shell=True, cwd=WORK_DIRECTORY)


def ccache_update_symlinks():
    cmd = "update-ccache-symlinks ||:"
    command(cmd, shell=True)


def ccache_show_config():
    cmd = "ccache --show-config ||:"
    command(cmd, shell=True)


def ccache_show_stats():
    cmd = "ccache --show-stats ||:"
    command(cmd, shell=True)


def dir_name(name: str) -> str:
    if not os.path.isabs(name):
        name = os.path.abspath(os.path.join(os.getcwd(), name))
    return name


def git_commit_hash():
    cmd = "git rev-parse HEAD"
    logging.info("Run command: %s", cmd)
    return subprocess.check_output(cmd, shell=True, cwd=WORK_DIRECTORY).decode(sys.stdout.encoding).strip()


def git_commit_date():
    cmd = f"git show -s --format=%ci {git_commit_hash()}"
    logging.info("Run command: %s", cmd)
    return subprocess.check_output(cmd, shell=True, cwd=WORK_DIRECTORY).decode(sys.stdout.encoding).strip()


def git_config():
    cmd = f"git config --global --add safe.directory {WORK_DIRECTORY}"
    command(cmd, shell=True)


def read_versions() -> Dict[str, Union[int, str]]:
    versions = {}
    with open(f"{WORK_DIRECTORY}/{VERSION_FILE}", "r", encoding="utf-8") as vf:
        for line in vf:
            line = line.strip()
            if not line.startswith("SET("):
                continue

            value = 0  # type: Union[int, str]
            name, value = line[4:-1].split(maxsplit=1)
            try:
                value = int(value)
            except ValueError:
                pass
            versions[name] = value
    return versions


def load_profile(name: str) -> Dict[str, str]:
    result: Dict[str, str] = dict()
    with open(os.path.join(BUILDER_PROFILE_DIRECTORY, name)) as lines:
        for line in lines:
            line = line.strip()
            if line.startswith("#"):
                continue
            conf = line.split("=")
            if len(conf) == 2:
                result[conf[0]] = conf[1]
    return result


def prepare_build(compiler: str, arch: str, profile: str, build_type: str, with_test: bool, with_shared_libraries: bool, with_clang_tidy: bool, with_sanitizer: str, with_coverage: bool, package: bool, official: bool) -> Dict[str, str]:
    git_config()
    cmake = load_profile(profile)

    cmake["-DCMAKE_C_COMPILER"] = compiler
    cmake["-DCMAKE_CXX_COMPILER"] = compiler.replace("gcc", "g++").replace("clang", "clang++")
    cmake["-DCMAKE_INSTALL_PREFIX"] = "/usr"
    cmake["-DCMAKE_INSTALL_SYSCONFDIR"] = "/etc"
    cmake["-DCMAKE_INSTALL_LOCALSTATEDIR"] = "/var"
    cmake["-DENABLE_THINLTO"] = "OFF"
    # disable rust api
    cmake["-DENABLE_RUST"] = "OFF"
    cmake["-DCMAKE_BUILD_TYPE"] = build_type
    cmake["-DVERSION_DATE"] = f"'{git_commit_date()}'"
    cmake["-DVERSION_GITHASH"] = git_commit_hash()

    if arch == "linux-x86_64":
        cmake["-DCMAKE_TOOLCHAIN_FILE"] = f"{WORK_DIRECTORY}/cmake/linux/toolchain-x86_64.cmake"
    elif arch == "linux-aarch64":
        cmake["-DCMAKE_TOOLCHAIN_FILE"] = f"{WORK_DIRECTORY}/cmake/linux/toolchain-aarch64.cmake"
    elif arch == "linux-ppc64le":
        cmake["-DCMAKE_TOOLCHAIN_FILE"] = f"{WORK_DIRECTORY}/cmake/linux/toolchain-ppc64le.cmake"
    elif arch == "darwin-x86_64":
        cmake["-DCMAKE_AR:FILEPATH"] = f"{BUILDER}/cctools/bin/x86_64-apple-darwin-ar"
        cmake["-DCMAKE_INSTALL_NAME_TOOL"] = f"{BUILDER}/cctools/bin/x86_64-apple-darwin-install_name_tool"
        cmake["-DCMAKE_RANLIB:FILEPATH"] = f"{BUILDER}/cctools/bin/x86_64-apple-darwin-ranlib"
        cmake["-DLINKER_NAME"] = f"{BUILDER}/cctools/bin/x86_64-apple-darwin-ld"
        cmake["-DCMAKE_TOOLCHAIN_FILE"] = f"{WORK_DIRECTORY}/cmake/darwin/toolchain-x86_64.cmake"
        cmake["-DCMAKE_OSX_SYSROOT"] = f"{BUILDER}/toolchain/darwin-x86_64"
    elif arch == "darwin-aarch64":
        cmake["-DCMAKE_AR:FILEPATH"] = f"{BUILDER}/cctools/bin/aarch64-apple-darwin-ar"
        cmake["-DCMAKE_INSTALL_NAME_TOOL"] = f"{BUILDER}/cctools/bin/aarch64-apple-darwin-install_name_tool"
        cmake["-DCMAKE_RANLIB:FILEPATH"] = f"{BUILDER}/cctools/bin/aarch64-apple-darwin-ranlib"
        cmake["-DLINKER_NAME"] = f"{BUILDER}/cctools/bin/aarch64-apple-darwin-ld"
        cmake["-DCMAKE_TOOLCHAIN_FILE"] = f"{WORK_DIRECTORY}/cmake/darwin/toolchain-aarch64.cmake"
        cmake["-DCMAKE_OSX_SYSROOT"] = f"{BUILDER}/toolchain/darwin-aarch64"
    elif arch == "freebsd-x86_64":
        cmake["-DCMAKE_TOOLCHAIN_FILE"] = f"{WORK_DIRECTORY}/cmake/freebsd/toolchain-x86_64.cmake"

    if with_test:
        cmake["-DENABLE_TESTS"] = "ON"

    if with_shared_libraries:
        cmake["-DUSE_STATIC_LIBRARIES"] = "OFF"
        cmake["-DSPLIT_SHARED_LIBRARIES"] = "ON"
        cmake["-DENABLE_UTILS"] = "ON"

    if with_clang_tidy:
        cmake["-DENABLE_CLANG_TIDY"] = "ON"
        cmake["-DENABLE_TESTS"] = "ON"
        cmake["-DENABLE_EXAMPLES"] = "ON"
        cmake["-DENABLE_UTILS"] = "ON"

    if with_sanitizer != '':
        cmake["-DSANITIZE"] = with_sanitizer

    if with_sanitizer == 'memory':
        cmake["-DENABLE_EMBEDDED_COMPILER"] = "OFF"
        cmake["-DENABLE_CLICKHOUSE_ALL"] = "OFF"
        cmake["-DENABLE_CLICKHOUSE_SERVER"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_CLIENT"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_FORMAT"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_LOCAL"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_COMPRESSOR"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_KEEPER"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_COPIER"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_EXTRACT_FROM_CONFIG"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_ODBC_BRIDGE"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_KEEPER_CONVERTER"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_LIBRARY_BRIDGE"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_KEEPER_CONVERTER"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_OBFUSCATOR"] = "ON"
        cmake["-DENABLE_CLICKHOUSE_INSTALL"] = "ON"
    # else:
    #     cmake["-DSANITIZE"] = "''"

    if with_coverage:
        cmake["-DWITH_COVERAGE"] = "ON"

    if official:
        cmake["-DCLICKHOUSE_OFFICIAL_BUILD"] = "ON"

    if package:
        cmake["-DENABLE_TESTS"] = "OFF"
        cmake["-DENABLE_UTILS"] = "OFF"
        cmake["-DCMAKE_EXPORT_NO_PACKAGE_REGISTRY"] = "ON"
        cmake["-DCMAKE_FIND_PACKAGE_NO_PACKAGE_REGISTRY"] = "ON"
        cmake["-DCMAKE_AUTOGEN_VERBOSE"] = "ON"

        if build_type in ["Release", "RelWithDebInfo"]:
            if build_type not in ["RelWithDebInfo"]:
                cmake["-DSPLIT_DEBUG_SYMBOLS"] = "ON"
            if with_sanitizer == '':
                cmake["-DBUILD_STANDALONE_KEEPER"] = "ON"

    return cmake


def build_diagnostics(arch: str, name: str):
    go_os, go_arch = arch.split("-", maxsplit=1)
    if go_arch == "x86_64":
        go_arch = "amd64"
    if go_arch == "aarch64":
        go_arch = "arm64"
    diagnostics_directory = f"{WORK_DIRECTORY}/programs/diagnostics"
    diagnostics = f"{WORK_DIRECTORY}/programs/{name.lower()}-diagnostics"

    if not os.path.isdir(diagnostics_directory):
        with open(diagnostics, "w") as script:
            script.write("#!/bin/sh")
            script.write("\n")
            script.write("echo 'Not implemented for this type of package'")
        os.chmod(diagnostics, 0o755)
        return

    cmd = "make test-no-docker"
    command(cmd, shell=True, cwd=diagnostics_directory)

    version = read_versions().get("VERSION_STRING")
    cmd = f"GOOS={go_os} GOARCH={go_arch} VERSION={version} CGO_ENABLED=0 make build"
    command(cmd, shell=True, cwd=diagnostics_directory)
    os.rename(f"{diagnostics_directory}/clickhouse-diagnostics", diagnostics)


def build(arch: str, build_jobs: int, cmake: Dict[str, str]):
    target_os, target_arch = arch.split("-", maxsplit=1)

    warp = [
        'LD_LIBRARY_PATH=/usr/lib/llvm-${LLVM_VERSION}/lib:${LD_LIBRARY_PATH}'
    ]

    # if target_arch == "x86_64" and target_os not in ["freebsd"]:
    #     warp.append('. /opt/intel/oneapi/mkl/${INTEL_ONEAPI_VERSION}/env/vars.sh')

    warp.append(" ")  # donot remove

    cmd = f"mkdir -pv {BUILD_DIRECTORY}"
    command(cmd, shell=True, cwd=WORK_DIRECTORY)

    cmd = "rm -fv CMakeCache.txt"
    command(cmd, shell=True, cwd=BUILD_DIRECTORY)

    if "-DSANITIZE" in cmake.keys() and cmake["-DSANITIZE"] == "address":
        cmd = "cmake --debug-trycompile -DCMAKE_VERBOSE_MAKEFILE=1 -LA -DENABLE_CHECK_HEAVY_BUILDS=OFF"
    else:
        cmd = "cmake --debug-trycompile -DCMAKE_VERBOSE_MAKEFILE=1 -LA -DENABLE_CHECK_HEAVY_BUILDS=ON"
    for k, v in cmake.items():
        logging.debug("CMAKE: %s = %s", k, v)
        cmd += f" {k}={v}"
    cmd += " .."
    logging.info("Run command: %s", cmd)

    cmd = "; ".join(warp) + cmd
    subprocess.check_call(cmd, shell=True, cwd=BUILD_DIRECTORY)

    build_target = "clickhouse-bundle"
    ninja = ""
    if cmake.get("-DENABLE_CLANG_TIDY") == "ON":
        ninja = "-k0 "

    if build_jobs > 0:
        ninja += f"-j{build_jobs} "

    cmd = f"ninja {ninja} {build_target}"
    logging.info("Run command: %s", cmd)
    cmd = "; ".join(warp) + cmd
    subprocess.check_call(cmd, shell=True, cwd=BUILD_DIRECTORY)


def package(name: str, arch: str, package: bool, with_sanitizer: str, build_type: str, output: str):
    cmd = f"DESTDIR={output} ninja install"
    command(cmd, shell=True, cwd=BUILD_DIRECTORY)

    if name != "ClickHouse":
        cmd = f"for src in `find * -type d -name 'clickhouse*' -print`;do dst=$(echo $src | sed 's/clickhouse/{name.lower()}/'); mv $src $dst; done"
        command(cmd, shell=True, cwd=f"{output}/etc")

        cmd = f"for src in `find * -type f -iname 'clickhouse*' -print`;do dst=$(echo $src | sed 's/clickhouse/{name.lower()}/'); mv $src $dst; done"
        command(cmd, shell=True, cwd=f"{output}/usr/bin")
        command(cmd, shell=True, cwd=f"{output}/usr/lib/debug/usr/bin")

        # cmd = f"for link in `find * -type l -iname 'clickhouse*' -print`;do src=$(readlink $link | sed 's/clickhouse/{name.lower()}/'); dst=$(echo $link | sed 's/clickhouse/{name.lower()}/'); ln -sv $src $dst; done"
        cmd = f"for link in `find * -type l -iname 'clickhouse*' -print`;do cmd=$(echo $link '$@' | sed 's/clickhouse-/{name.lower()} /'); dst=$(echo $link | sed 's/clickhouse/{name.lower()}/'); echo $cmd > $dst; done"
        command(cmd, shell=True, cwd=f"{output}/usr/bin")

        cmd = f"chmod a+x {name.lower()}*"
        command(cmd, shell=True, cwd=f"{output}/usr/bin")

        cmd = "find * -type l -iname 'clickhouse*' -delete"
        command(cmd, shell=True, cwd=f"{output}/usr/bin")

    cmd = f"cp -fv programs/{name.lower()}-diagnostics {output}/usr/bin"
    command(cmd, shell=True, cwd=WORK_DIRECTORY)

    docs = [
        "LICENSE",
        "NOTICE.txt",
    ]

    docs_directory = f"usr/share/doc/{name.lower()}"
    cmd = f"mkdir -pv {docs_directory}"
    command(cmd, shell=True, cwd=output)

    for doc in docs:
        cmd = f"cp -fv {WORK_DIRECTORY}/{doc} {output}/{docs_directory}/"
        command(cmd, shell=True, cwd=WORK_DIRECTORY)

    cmd = f"rm -frv usr/cmake"
    command(cmd, shell=True, cwd=output)

    cmd = f'find usr/share/bash-completion/completions ! -iname "{name.lower()}*" -type f -delete'
    command(cmd, shell=True, cwd=output)

    if package:
        version = read_versions().get("VERSION_STRING")
        target_os, target_arch = arch.split("-", maxsplit=1)
        if target_arch == "x86_64":
            target_arch = "amd64"
        if target_arch == "aarch64":
            target_arch = "arm64"

        # tgz
        pkg = f"{name.lower()}-{version}-{target_arch}"
        cmd = f"find . \( -type f -or -type l \) -and ! \( -name '*.debug' -o -name '*.a' -o -name '*.tgz' -o -name '*.deb' -o -name '*.rpm' -o -name '*.apk' \) | tar --transform 's,^\.,{pkg},' -cvf {pkg}.tgz -T -"
        command(cmd, shell=True, cwd=output)

        pkg = f"{name.lower()}-dbg-{version}-{target_arch}"
        cmd = f"find . \( -type f -or -type l \) -and \( -name '*.debug' -o -name LICENSE -o -name NOTICE.txt \) | tar --transform 's,^\.,{pkg},' -cvf {pkg}.tgz -T -"
        command(cmd, shell=True, cwd=output)

        # deb/rpm/apk
        cmd = f"cp -fv {BUILDER_PACKAGE_DIRECTORY}/{name.lower()}-* {output}/"
        command(cmd, shell=True, cwd=WORK_DIRECTORY)

        if with_sanitizer == "address":
            version += "+asan"
        if with_sanitizer == "thread":
            version += "+tsan"
        if with_sanitizer == "memory":
            version += "+msan"
        if with_sanitizer == "undefined":
            version += "+ubsan"

        if build_type == "Debug":
            version += "+debug"

        packages = ["deb", "rpm", "apk"]
        for pkg in packages:
            cmd = f'for conf in `find . -iname "*.yaml"`;do nfpm package --config $conf --packager {pkg}; done'
            command(cmd, shell=True, cwd=output, env={"OS": target_os, "ARCH": target_arch, "VERSION_STRING": version})

        # cleanup
        cmd = "find ! \( -name '*.tgz' -o -name '*.deb' -o -name '*.rpm' -o -name '*.apk' \) -delete"
        command(cmd, shell=True, cwd=output)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    logging.debug("BUILDER: %s", IMAGE)
    logging.debug("BUILDER_DIRECTORY: %s", BUILDER_DIRECTORY)
    logging.debug("BUILDER_DOCKERFILE: %s", BUILDER_DOCKERFILE)
    logging.debug("BUILDER_PROFILE_DIRECTORY: %s", BUILDER_PROFILE_DIRECTORY)
    logging.debug("BUILDER_PACKAGE_DIRECTORY: %s", BUILDER_PACKAGE_DIRECTORY)
    logging.debug("WORK_DIRECTORY: %s", WORK_DIRECTORY)
    logging.debug("WORK_DIRECTORY_NAME: %s", WORK_DIRECTORY_NAME)
    logging.debug("BUILD_DIRECTORY: %s", BUILD_DIRECTORY)

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="building tool",
    )

    # compiler = "clang-13"
    parser.add_argument(
        "--compiler",
        choices=(
            "clang-15",
            "clang-16",
        ),
        default="clang-15",
    )

    parser.add_argument(
        "--arch",
        choices=(
            "linux-x86_64",
            "linux-aarch64",
            "linux-ppc64le",
            "darwin-x86_64",
            "darwin-aarch64",
            "freebsd-x86_64"
        ),
        default="linux-x86_64",
    )

    parser.add_argument(
        "--profile",
        default="default",
    )

    parser.add_argument(
        "--name",
        choices=(
            "ClickHouse",
            "MyScale",
        ),
        default="ClickHouse",
    )

    parser.add_argument(
        "--build-type",
        choices=(
            "Debug",
            "Release",
            "RelWithDebInfo",
            "MinSizeRel",
        ),
        default="Release",
    )

    parser.add_argument(
        "--build-jobs",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--with-test",
        action="store_true",
    )

    parser.add_argument(
        "--with-shared-libraries",
        action="store_true",
    )

    parser.add_argument(
        "--with-clang-tidy",
        action="store_true",
    )

    parser.add_argument(
        "--with-sanitizer",
        choices=(
            "address",
            "thread",
            "memory",
            "undefined",
            "",
        ),
        default="",
    )

    parser.add_argument(
        "--with-coverage",
        action="store_true",
    )

    parser.add_argument(
        "--package",
        action="store_true",
    )

    parser.add_argument(
        "--official",
        action="store_true",
    )

    parser.add_argument(
        "--docker",
        action="store_true",
    )

    parser.add_argument(
        "--image-version",
        default="2.9.1",
    )

    parser.add_argument(
        "--force-build-image",
        action="store_true",
    )

    parser.add_argument(
        "--ccache",
        default=os.getenv("HOME", "") + "/.ccache",
        type=dir_name,
    )

    parser.add_argument(
        "--output",
        type=dir_name,
        required=True,
    )

    args = parser.parse_args()
    logging.debug("OPTIONS: %s", vars(args))

    if args.docker:
        image = f"{IMAGE}:{args.image_version}"
        if args.force_build_image:
            build_image(image, BUILDER_DOCKERFILE)
        elif not check_image_exists_locally(image):
            pull_image(image)
        argv = sys.argv[1:]
        options = list()
        while len(argv) > 0:
            arg = argv.pop(0)
            if arg in ['--docker', "--force-build-image"]:
                continue
            if arg in ["--image-version", "--ccache"]:
                argv.pop(0)
                continue
            if arg == '--output':
                argv.pop(0)
                options.append(arg)
                options.append(f"{BUILDER}/output")
                continue
            options.append(arg)
        logging.info("Run build in docker, options: %s", options)
        run_docker_builder(image, True, args.ccache, args.output, options)
        exit(0)

    # build_diagnostics(args.arch, args.name)

    cmake = prepare_build(args.compiler, args.arch, args.profile, args.build_type, args.with_test, args.with_shared_libraries, args.with_clang_tidy, args.with_sanitizer, args.with_coverage, args.package, args.official)

    build(args.arch, args.build_jobs, cmake)
    ccache_show_stats()
    package(args.name, args.arch, args.package, args.with_sanitizer, args.build_type, args.output)
